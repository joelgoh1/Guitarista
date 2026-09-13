"""Background prefetch for noodle mode.

One asyncio task. Every ``interval`` seconds it refreshes the listening pool if it has gone
stale and then tops the pool up to ``settings.noodle_prefetch_target`` ready tabs, one job at a
time and only while no other job is running -- a background convenience must never compete with
something the user asked for.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.llm import LLMClient
from guitarista_api.adapters.spotify import SpotifyClient
from guitarista_api.adapters.spotify_user import SpotifyUserClient
from guitarista_api.db.repos_noodle import PoolRepo
from guitarista_api.domain.job import CandidateRef, Job, TabRequest
from guitarista_api.domain.noodle import PoolEntry
from guitarista_api.domain.song import SongQuery
from guitarista_api.jobs.manager import TERMINAL_STATUSES, JobManager
from guitarista_api.services.job_launch import launch_tab_job
from guitarista_api.services.listening_pool import PoolSummary, build_pool
from guitarista_api.settings import Settings
from guitarista_api.sources.base import TabSource

log = structlog.get_logger(__name__)

DEFAULT_INTERVAL = 60.0
MAX_ATTEMPTS = 2
"""A pool entry that failed this many times is left alone (``next_prefetchable`` enforces it)."""

LaunchFn = Callable[..., Awaitable[Job]]
BuildFn = Callable[..., Awaitable[PoolSummary]]


class NoodlePrefetcher:
    """Keeps a handful of tabs from the listening pool warm. Start/stop are idempotent."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        manager: JobManager,
        http: httpx.AsyncClient,
        sources: Sequence[TabSource],
        spotify_user: SpotifyUserClient,
        spotify: SpotifyClient | None = None,
        llm: LLMClient | None = None,
        interval: float = DEFAULT_INTERVAL,
        job_timeout: float | None = None,
        poll_interval: float = 0.25,
        launch: LaunchFn = launch_tab_job,
        build: BuildFn = build_pool,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.manager = manager
        self.http = http
        self.sources = sources
        self.spotify_user = spotify_user
        self.spotify: SpotifyClient = spotify or spotify_user
        self.llm = llm
        self.interval = interval
        self.job_timeout = (
            job_timeout if job_timeout is not None else settings.tier_timeout_songsterr * 3 + 30
        )
        self.poll_interval = poll_interval
        self._launch = launch
        self._build = build
        self._task: asyncio.Task[None] | None = None
        self._own_jobs: set[str] = set()

    # ------------------------------------------------------------------ lifecycle

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the loop if it is not already running (safe to call repeatedly)."""
        if self.running:
            return
        self._task = asyncio.create_task(self._run(), name="noodle-prefetch")
        log.info("noodle.prefetcher_started", interval=self.interval)

    async def stop(self) -> None:
        """Cancel the loop and wait for it to unwind."""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("noodle.prefetcher_stopped")

    async def _run(self) -> None:
        try:
            while True:
                try:
                    await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception:  # one bad cycle must not kill the loop
                    log.warning("noodle.tick_failed", exc_info=True)
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------ one cycle

    async def tick(self) -> None:
        """Refresh the pool if stale, then fill it up to the target, one job at a time."""
        if not self.settings.noodle_enabled:
            return
        if not await self.spotify_user.is_connected():
            return
        await self._build(
            client=self.spotify_user,
            session_factory=self.session_factory,
            sources=self.sources,
            settings=self.settings,
        )
        target = self.settings.noodle_prefetch_target
        while target > 0:
            if self._busy():
                log.debug("noodle.prefetch_deferred")
                return
            async with self.session_factory() as session:
                repo = PoolRepo(session)
                ready = len(await repo.list(statuses=["ready"], limit=target))
                if ready >= target:
                    return
                queue = await repo.next_prefetchable(1, max_attempts=MAX_ATTEMPTS)
            if not queue:
                return
            await self._prefetch(queue[0])

    def _busy(self) -> bool:
        """True when a job we did not start is running."""
        return any(job_id not in self._own_jobs for job_id in self.manager.running_ids())

    async def _prefetch(self, entry: PoolEntry) -> None:
        body = TabRequest(
            song=SongQuery(spotify_url=entry.spotify_url),
            candidate=(
                CandidateRef(source=entry.candidate.source, external_id=entry.candidate.external_id)
                if entry.candidate is not None
                else None
            ),
            tiers=["songsterr"],
            origin="noodle",
        )
        async with self.session_factory() as session:
            await PoolRepo(session).set_status(entry.spotify_id, "queued")
        try:
            job = await self._launch(
                body=body,
                settings=self.settings,
                manager=self.manager,
                http=self.http,
                session_factory=self.session_factory,
                spotify=self.spotify,
                llm=self.llm,
                sources=self.sources,
            )
        except Exception as exc:
            await self._fail(entry, f"{type(exc).__name__}: {exc}")
            return
        self._own_jobs.add(job.id)
        async with self.session_factory() as session:
            await PoolRepo(session).set_status(entry.spotify_id, "queued", job_id=job.id)
        try:
            final = await self._await_job(job.id)
        finally:
            self._own_jobs.discard(job.id)
        if final is not None and final.status == "done" and final.tab_id:
            async with self.session_factory() as session:
                await PoolRepo(session).mark_tab(
                    entry.spotify_id, tab_id=final.tab_id, song_id=final.song_id
                )
            log.info("noodle.prefetched", spotify_id=entry.spotify_id, tab_id=final.tab_id)
            return
        reason = (final.error if final is not None else None) or "prefetch job did not finish"
        await self._fail(entry, reason)

    async def _fail(self, entry: PoolEntry, error: str) -> None:
        async with self.session_factory() as session:
            await PoolRepo(session).set_status(
                entry.spotify_id, "failed", error=error[:500], bump_attempts=True
            )
        log.info("noodle.prefetch_failed", spotify_id=entry.spotify_id, error=error)

    async def _await_job(self, job_id: str) -> Job | None:
        """Poll the manager until the job reaches a terminal status (or the timeout elapses)."""
        waited = 0.0
        while True:
            job = await self.manager.get(job_id)
            if job is not None and job.status in TERMINAL_STATUSES:
                return job
            if waited >= self.job_timeout:
                log.warning("noodle.prefetch_timeout", job_id=job_id)
                return job
            await asyncio.sleep(self.poll_interval)
            waited += self.poll_interval
