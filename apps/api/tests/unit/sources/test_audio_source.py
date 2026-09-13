from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from guitarista_api.adapters.ml_sidecar import MLSidecar
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.jobs.context import JobContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.sources.audio import AudioSource
from guitarista_api.sources.base import SourceError

SONG = Song(id="s1", title="Song", artist="Artist")


@pytest.fixture
async def make_ctx(tmp_path: Path) -> AsyncIterator[Any]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    manager = JobManager(factory)
    clients: list[httpx.AsyncClient] = []

    def _make(settings, request: TabRequest | None = None) -> JobContext:
        http = httpx.AsyncClient()
        clients.append(http)
        job = Job(request=request or TabRequest(song=SongQuery(raw="x")))
        return JobContext(
            job, settings=settings, http=http, manager=manager, session_factory=factory
        )

    yield _make
    for c in clients:
        await c.aclose()
    await engine.dispose()


def settings_for(tmp_path: Path, **overrides: Any):
    from guitarista_api.settings import Settings

    return Settings(data_dir=tmp_path / "data", _env_file=None, **overrides)


async def test_can_handle_reasons_matrix(tmp_path: Path, make_ctx, fake_ml_cmd: str) -> None:
    upload = TabRequest(upload_id="abc")
    no_upload = TabRequest(song=SongQuery(raw="x"))

    src = AudioSource()
    ok, why = src.can_handle(
        upload, SONG, make_ctx(settings_for(tmp_path, enable_audio_tier=False))
    )
    assert (ok, why) == (False, "audio tier disabled (GUITARISTA_ENABLE_AUDIO_TIER=false)")

    ok, why = src.can_handle(no_upload, SONG, make_ctx(settings_for(tmp_path, enable_ytdlp=False)))
    assert not ok and "yt-dlp fetching is disabled" in (why or "")

    ok, why = src.can_handle(
        no_upload, SONG, make_ctx(settings_for(tmp_path, enable_ytdlp=True, ytdlp_bin="nope-ytdlp"))
    )
    assert not ok and "nope-ytdlp" in (why or "") and "brew install yt-dlp" in (why or "")

    ok, why = src.can_handle(
        upload, SONG, make_ctx(settings_for(tmp_path, ffmpeg_bin="nope-ffmpeg"))
    )
    assert not ok and "ffmpeg" in (why or "") and "brew install ffmpeg" in (why or "")

    # sidecar probe failed (command missing) -> actionable message once probed
    bad = AudioSource(ml_sidecar=MLSidecar("/no/such/guitarista-ml"))
    ctx = make_ctx(settings_for(tmp_path))
    assert bad.can_handle(upload, SONG, ctx) == (True, None)  # not probed yet: fetch decides
    await bad.sidecar_for(ctx.settings).probe()
    ok, why = bad.can_handle(upload, SONG, ctx)
    assert not ok and "ML sidecar unavailable" in (why or "") and "uv sync" in (why or "")
    with pytest.raises(SourceError, match="uv sync"):
        await bad.fetch(upload, SONG, ctx)

    # happy path: probe from settings.ml_cmd (fake), upload present
    good = AudioSource()
    ctx = make_ctx(settings_for(tmp_path, ml_cmd=fake_ml_cmd))
    caps = await good.sidecar_for(ctx.settings).probe()
    assert caps is not None and caps.basic_pitch
    assert good.can_handle(upload, SONG, ctx) == (True, None)


async def test_fetch_reports_missing_upload(tmp_path: Path, make_ctx, fake_ml_cmd: str) -> None:
    src = AudioSource()
    ctx = make_ctx(settings_for(tmp_path, ml_cmd=fake_ml_cmd))
    with pytest.raises(SourceError, match="not found"):
        await src.fetch(TabRequest(upload_id="ghost"), SONG, ctx)


async def test_fetch_without_upload_and_ytdlp_disabled(
    tmp_path: Path, make_ctx, fake_ml_cmd
) -> None:
    src = AudioSource()
    ctx = make_ctx(settings_for(tmp_path, ml_cmd=fake_ml_cmd, enable_ytdlp=False))
    with pytest.raises(SourceError, match="yt-dlp fetching is disabled"):
        await src.fetch(TabRequest(song=SongQuery(raw="x")), SONG, ctx)
