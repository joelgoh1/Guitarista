from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.db.repos_noodle import PoolRepo
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.candidate import Candidate
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.domain.noodle import PoolEntry
from guitarista_api.jobs.prefetch import NoodlePrefetcher
from guitarista_api.services.listening_pool import PoolSummary
from guitarista_api.settings import Settings


class FakeManager:
    """A manager whose jobs are already finished; ``running`` fakes a competing user job."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.running: list[str] = []

    def running_ids(self) -> list[str]:
        return list(self.running)

    async def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)


class FakeLauncher:
    """Stands in for ``launch_tab_job``: records the request, returns a terminal job."""

    def __init__(self, manager: FakeManager, *, status: str = "done") -> None:
        self.manager = manager
        self.status = status
        self.requests: list[TabRequest] = []

    async def __call__(self, *, body: TabRequest, **_: Any) -> Job:
        self.requests.append(body)
        job = Job(request=body)
        job.status = self.status  # type: ignore[assignment]
        if self.status == "done":
            job.tab_id = f"tab-{len(self.requests)}"
            job.song_id = f"song-{len(self.requests)}"
        else:
            job.error = "songsterr said no"
        self.manager.jobs[job.id] = job
        return job


async def noop_build(**_: Any) -> PoolSummary:
    return PoolSummary(skipped=True)


class FakeSpotifyUser:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.http = None

    async def is_connected(self) -> bool:
        return self.connected


@pytest.fixture
async def factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'prefetch.db'}")
    await create_all(engine)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data", noodle_prefetch_target=2, noodle_enabled=True, _env_file=None
    )


def pool_entry(spotify_id: str, score: float) -> PoolEntry:
    return PoolEntry(
        spotify_id=spotify_id,
        title=f"Song {spotify_id}",
        artist="Oasis",
        score=score,
        availability="available",
        candidate=Candidate(
            source="songsterr", external_id=f"s{spotify_id}", title="x", artist="y", score=0.9
        ),
    )


async def seed(factory, *entries: PoolEntry) -> None:
    async with factory() as session:
        await PoolRepo(session).upsert_many(entries)
        for entry in entries:
            # upsert_many preserves candidate/availability only for *new* rows, so set explicitly
            await PoolRepo(session).set_status(
                entry.spotify_id,
                "new",
                availability="available",
                candidate_json=entry.candidate.model_dump(mode="json") if entry.candidate else None,
            )


async def make_prefetcher(
    factory, settings, manager: FakeManager, launcher: FakeLauncher, **kwargs: Any
) -> AsyncIterator[NoodlePrefetcher]:
    async with httpx.AsyncClient() as http:
        yield NoodlePrefetcher(
            settings=settings,
            session_factory=factory,
            manager=manager,  # type: ignore[arg-type]
            http=http,
            sources=[],
            spotify_user=FakeSpotifyUser(),  # type: ignore[arg-type]
            interval=0.01,
            poll_interval=0.001,
            job_timeout=1.0,
            launch=launcher,
            build=kwargs.pop("build", noop_build),
            **kwargs,
        )


async def test_tick_fills_to_target_one_at_a_time(factory, settings) -> None:
    await seed(factory, pool_entry("a", 0.9), pool_entry("b", 0.8), pool_entry("c", 0.7))
    manager = FakeManager()
    launcher = FakeLauncher(manager)
    async for p in make_prefetcher(factory, settings, manager, launcher):
        await p.tick()

    # target is 2, so exactly two jobs ran -- best score first
    assert len(launcher.requests) == 2
    req = launcher.requests[0]
    assert req.origin == "noodle" and req.tiers == ["songsterr"]
    assert req.song is not None
    assert req.song.spotify_url == "https://open.spotify.com/track/a"
    assert req.candidate is not None and req.candidate.external_id == "sa"
    async with factory() as session:
        ready = await PoolRepo(session).list(statuses=["ready"])
    assert [e.spotify_id for e in ready] == ["a", "b"]
    assert ready[0].tab_id == "tab-1" and ready[0].song_id == "song-1"
    async with factory() as session:
        untouched = await PoolRepo(session).get("c")
    assert untouched is not None and untouched.status == "new"


async def test_tick_skips_while_a_user_job_runs(factory, settings) -> None:
    await seed(factory, pool_entry("a", 0.9))
    manager = FakeManager()
    manager.running = ["someone-elses-job"]
    launcher = FakeLauncher(manager)
    async for p in make_prefetcher(factory, settings, manager, launcher):
        await p.tick()
    assert launcher.requests == []
    async with factory() as session:
        assert (await PoolRepo(session).get("a")).status == "new"


async def test_tick_does_nothing_when_disconnected_or_disabled(factory, settings) -> None:
    await seed(factory, pool_entry("a", 0.9))
    manager = FakeManager()
    launcher = FakeLauncher(manager)
    async for p in make_prefetcher(factory, settings, manager, launcher):
        p.spotify_user.connected = False  # type: ignore[attr-defined]
        await p.tick()
        p.spotify_user.connected = True  # type: ignore[attr-defined]
        p.settings = settings.model_copy(update={"noodle_enabled": False})
        await p.tick()
    assert launcher.requests == []


async def test_failures_bump_attempts_and_stop_after_two(factory, settings) -> None:
    await seed(factory, pool_entry("a", 0.9))
    manager = FakeManager()
    launcher = FakeLauncher(manager, status="failed")
    async for p in make_prefetcher(factory, settings, manager, launcher):
        await p.tick()
        async with factory() as session:
            entry = await PoolRepo(session).get("a")
        assert entry is not None and entry.status == "failed" and entry.attempts == 2
        assert entry.error == "songsterr said no"
        assert len(launcher.requests) == 2  # two attempts inside the one tick, then it gives up
        await p.tick()  # a later cycle must not retry a spent entry
    assert len(launcher.requests) == 2


async def test_start_is_idempotent_and_stop_cancels_cleanly(factory, settings) -> None:
    await seed(factory, pool_entry("a", 0.9))
    manager = FakeManager()
    launcher = FakeLauncher(manager)
    async for p in make_prefetcher(factory, settings, manager, launcher):
        p.start()
        task = p._task
        p.start()
        assert p._task is task and p.running
        await asyncio.sleep(0.05)
        await p.stop()
        assert not p.running and task is not None and task.cancelled() or task.done()
        await p.stop()  # stopping twice is fine
    assert launcher.requests  # the loop did real work before being cancelled


async def test_loop_survives_a_failing_tick(factory, settings) -> None:
    manager = FakeManager()
    launcher = FakeLauncher(manager)
    calls = 0

    async def boom(**_: Any) -> PoolSummary:
        nonlocal calls
        calls += 1
        raise RuntimeError("spotify exploded")

    async for p in make_prefetcher(factory, settings, manager, launcher, build=boom):
        p.start()
        await asyncio.sleep(0.05)
        assert p.running
        await p.stop()
    assert calls >= 2
