"""In-process job registry: one asyncio Task per job, subscriber queues for SSE, SQLite writes.

Publishing order matters: the ``Job`` snapshot is persisted *before* fan-out so a client that
polls ``GET /jobs/{id}`` right after receiving an event sees the same state.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.db.repo import JobRepo
from guitarista_api.domain.job import Job
from guitarista_api.jobs.events import JobEvent, JobEventType

log = structlog.get_logger(__name__)

TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled", "interrupted"})
_END = None  # queue sentinel


class JobManager:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._jobs: dict[str, Job] = {}
        self._subscribers: dict[str, list[asyncio.Queue[JobEvent | None]]] = {}
        self._cancel_requested: set[str] = set()

    # ------------------------------------------------------------------ lifecycle

    async def submit(self, job: Job, coro_factory: Callable[[], Awaitable[None]]) -> Job:
        """Persist ``job`` (status queued) and start its task."""
        self._jobs[job.id] = job
        await self._persist(job)
        task = asyncio.create_task(self._guard(job, coro_factory), name=f"job-{job.id}")
        self._tasks[job.id] = task
        return job

    async def _guard(self, job: Job, coro_factory: Callable[[], Awaitable[None]]) -> None:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            if job.status not in TERMINAL_STATUSES:
                job.status = "cancelled"
                job.error = job.error or "cancelled"
                await self.publish(job, "error", {"error": job.error, "status": job.status})
        except Exception as exc:  # the runner should have handled this, but never leak
            log.exception("job.crashed", job_id=job.id)
            if job.status not in TERMINAL_STATUSES:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                await self.publish(job, "error", {"error": job.error, "status": job.status})
        finally:
            self._close(job.id)

    def _close(self, job_id: str) -> None:
        for queue in self._subscribers.pop(job_id, []):
            queue.put_nowait(_END)
        self._tasks.pop(job_id, None)
        self._cancel_requested.discard(job_id)

    async def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        self._cancel_requested.add(job_id)
        task.cancel()
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        return job_id in self._cancel_requested

    def running_ids(self) -> list[str]:
        return [job_id for job_id, task in self._tasks.items() if not task.done()]

    async def shutdown(self) -> None:
        tasks = [t for t in self._tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------ state

    async def get(self, job_id: str) -> Job | None:
        if job_id in self._jobs:
            return self._jobs[job_id]
        async with self.session_factory() as session:
            return await JobRepo(session).get(job_id)

    async def _persist(self, job: Job) -> None:
        job.updated_at = datetime.now(UTC)
        async with self.session_factory() as session:
            await JobRepo(session).upsert(job)

    async def publish(self, job: Job, event_type: JobEventType, payload: dict[str, Any]) -> None:
        """Persist the job snapshot, then fan the event out to subscribers."""
        await self._persist(job)
        event = JobEvent(
            type=event_type,
            job_id=job.id,
            payload={**payload, "job": job.model_dump(mode="json")},
        )
        for queue in list(self._subscribers.get(job.id, [])):
            queue.put_nowait(event)
        if job.status in TERMINAL_STATUSES:
            self._jobs.pop(job.id, None)

    # ------------------------------------------------------------------ streaming

    async def subscribe(self, job_id: str) -> AsyncIterator[JobEvent]:
        """Replay the current tier log as ``tier`` events, then stream live events until the end."""
        queue: asyncio.Queue[JobEvent | None] = asyncio.Queue()
        job = await self.get(job_id)
        if job is None:
            return
        live = job_id in self._tasks and not self._tasks[job_id].done()
        if live:
            self._subscribers.setdefault(job_id, []).append(queue)
        # Replay from the snapshot taken *after* subscribing so nothing is lost in between.
        snapshot = job.model_dump(mode="json")
        for entry in job.tiers:
            yield JobEvent(
                type="tier",
                job_id=job_id,
                payload={"tier": entry.model_dump(mode="json"), "job": snapshot, "replay": True},
            )
        if job.status in TERMINAL_STATUSES:
            yield _terminal_event(job)
            return
        if not live:
            return
        try:
            while True:
                event = await queue.get()
                if event is _END:
                    return
                yield event
        finally:
            subs = self._subscribers.get(job_id)
            if subs and queue in subs:
                subs.remove(queue)


def _terminal_event(job: Job) -> JobEvent:
    snapshot = job.model_dump(mode="json")
    if job.status == "done":
        return JobEvent(type="done", job_id=job.id, payload={"tab_id": job.tab_id, "job": snapshot})
    return JobEvent(
        type="error",
        job_id=job.id,
        payload={"error": job.error or job.status, "status": job.status, "job": snapshot},
    )
