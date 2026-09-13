from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.domain.tab import Tab, Track
from guitarista_api.jobs.context import JobContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.services.tier_runner import NoTabFound, TierRunner
from guitarista_api.settings import Settings
from guitarista_api.sources.base import SourceError, SourceResult


class FakeSource:
    deterministic = True

    def __init__(self, name: str, behaviour: str, *, delay: float = 0.0) -> None:
        self.name = name
        self.behaviour = behaviour
        self.delay = delay
        self.calls = 0

    def can_handle(self, request, song, ctx):
        if self.behaviour == "skip":
            return False, "not applicable here"
        return True, None

    async def fetch(self, request, song, ctx) -> SourceResult:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.behaviour == "fail":
            raise SourceError("nothing found", {"candidates": []})
        if self.behaviour == "crash":
            raise RuntimeError("boom")
        tab = Tab(title=song.title, tracks=[Track()])
        return SourceResult(tab=tab, detail={"picked": self.name}, message="ok")


@pytest.fixture
async def ctx(tmp_path: Path) -> AsyncIterator[JobContext]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    manager = JobManager(factory)
    job = Job(request=TabRequest(song=SongQuery(raw="x")))
    async with httpx.AsyncClient() as http:
        yield JobContext(
            job, settings=settings, http=http, manager=manager, session_factory=factory
        )
    await engine.dispose()


SONG = Song(id="s1", title="Wonderwall", artist="Oasis")
REQ = TabRequest(song=SongQuery(raw="oasis wonderwall"))


async def test_skip_then_fail_then_success_in_order(ctx: JobContext) -> None:
    sources = [
        FakeSource("songsterr", "skip"),
        FakeSource("ultimate_guitar", "fail"),
        FakeSource("audio", "ok"),
    ]
    result = await TierRunner(sources).run(REQ, SONG, ctx)
    assert result.tab.title == "Wonderwall"
    statuses = [(t.tier, t.status) for t in ctx.job.tiers]
    assert statuses == [
        ("songsterr", "skipped"),
        ("ultimate_guitar", "failed"),
        ("audio", "success"),
    ]
    assert ctx.job.tiers[0].message == "not applicable here"
    assert ctx.job.tiers[1].detail == {"candidates": []}
    assert ctx.job.tiers[2].detail["picked"] == "audio" and ctx.job.tiers[2].finished_at
    assert ctx.job.progress == 1.0


async def test_first_success_wins(ctx: JobContext) -> None:
    second = FakeSource("ultimate_guitar", "ok")
    await TierRunner([FakeSource("songsterr", "ok"), second]).run(REQ, SONG, ctx)
    assert second.calls == 0 and len(ctx.job.tiers) == 1


async def test_timeout_and_crash_are_logged_and_no_tab_found(ctx: JobContext) -> None:
    sources = [FakeSource("songsterr", "ok", delay=5), FakeSource("ultimate_guitar", "crash")]
    runner = TierRunner(sources, timeouts={"songsterr": 0.05})
    with pytest.raises(NoTabFound) as exc:
        await runner.run(REQ, SONG, ctx)
    assert [t.status for t in exc.value.tiers] == ["timeout", "failed"]
    assert "timed out" in (ctx.job.tiers[0].message or "")
    assert "RuntimeError" in (ctx.job.tiers[1].message or "")
    assert "songsterr: timeout" in str(exc.value)


async def test_requested_tiers_filter(ctx: JobContext) -> None:
    ss = FakeSource("songsterr", "ok")
    audio = FakeSource("audio", "ok")
    req = TabRequest(song=SongQuery(raw="x"), tiers=["audio"])
    await TierRunner([ss, audio]).run(req, SONG, ctx)
    assert ss.calls == 0 and audio.calls == 1


async def test_cancellation_marks_tier_cancelled(ctx: JobContext) -> None:
    runner = TierRunner([FakeSource("songsterr", "ok", delay=5)])
    task = asyncio.create_task(runner.run(REQ, SONG, ctx))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ctx.job.tiers[0].status == "cancelled"
