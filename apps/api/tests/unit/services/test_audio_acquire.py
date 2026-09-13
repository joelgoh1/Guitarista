"""``AudioPipeline._acquire``: audio_url bypasses search, and search picks a verified match."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from guitarista_api.adapters.ytdlp import YtCandidate
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services import audio_pipeline as ap
from guitarista_api.services.audio_pipeline import AudioPipeline
from guitarista_api.settings import Settings
from guitarista_api.sources.base import SourceError

SONG = Song(id="s1", title="Wonderwall", artist="Oasis", duration_s=259.0)


@pytest.fixture
async def ctx(tmp_path: Path) -> AsyncIterator[SourceContext]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(data_dir=tmp_path / "data", enable_ytdlp=True, _env_file=None)
    async with httpx.AsyncClient() as http:
        yield SourceContext(settings=settings, http=http, session_factory=factory)
    await engine.dispose()


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """Record what fetch_audio was asked to download, without shelling out."""
    seen: dict = {}

    async def fake_fetch_audio(target: str, out_dir: Path, *_: object, **__: object) -> Path:
        seen["target"] = target

        def write() -> Path:
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / "ytdlp.wav"
            path.write_bytes(b"RIFF")
            return path

        return await asyncio.to_thread(write)

    monkeypatch.setattr(ap, "fetch_audio", fake_fetch_audio)
    return seen


def yt(vid: str, title: str, uploader: str, duration_s: float) -> YtCandidate:
    return YtCandidate(
        video_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        title=title,
        uploader=uploader,
        duration_s=duration_s,
    )


def patch_search(monkeypatch: pytest.MonkeyPatch, candidates: list[YtCandidate]) -> dict:
    seen: dict = {}

    async def fake_search(query: str, **kwargs: object) -> list[YtCandidate]:
        seen["query"] = query
        return candidates

    monkeypatch.setattr(ap, "search_candidates", fake_search)
    return seen


async def acquire(
    ctx: SourceContext, request: TabRequest, tmp_path: Path
) -> tuple[Path, str, dict]:
    detail: dict = {}
    pipeline = AudioPipeline(sidecar=None)  # type: ignore[arg-type]
    path, ref = await pipeline._acquire(request, SONG, ctx, tmp_path / "work", detail)
    return path, ref, detail


async def test_audio_url_bypasses_search(
    ctx: SourceContext, tmp_path: Path, fake_download: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: object, **__: object) -> None:
        raise AssertionError("an explicit audio_url must not trigger a search")

    monkeypatch.setattr(ap, "search_candidates", boom)
    url = "https://www.youtube.com/watch?v=chosen"
    _, ref, detail = await acquire(ctx, TabRequest(song_id="s1", audio_url=url), tmp_path)
    assert fake_download["target"] == url
    assert ref == url
    assert detail["input"] == {"kind": "ytdlp_url", "url": url, "file": "ytdlp.wav"}


async def test_search_downloads_the_verified_match(
    ctx: SourceContext, tmp_path: Path, fake_download: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = patch_search(
        monkeypatch,
        [
            yt("live", "Wonderwall (Live in Dublin)", "WE ARE ROBOT", 257.0),
            yt("album", "Oasis - Wonderwall", "Oasis", 259.0),
        ],
    )
    _, ref, detail = await acquire(ctx, TabRequest(song_id="s1"), tmp_path)
    assert seen["query"] == "oasis wonderwall"
    assert fake_download["target"] == "https://www.youtube.com/watch?v=album"
    assert ref == "https://www.youtube.com/watch?v=album"
    assert detail["input"]["video_id"] == "album"
    assert detail["input"]["expected_duration_s"] == 259.0
    # Every candidate considered is logged so a wrong pick is explainable after the fact.
    assert {b["video_id"] for b in detail["input"]["considered"]} == {"album", "live"}


async def test_no_acceptable_match_fails_instead_of_transcribing_the_wrong_song(
    ctx: SourceContext, tmp_path: Path, fake_download: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_search(monkeypatch, [yt("x", "Some Unrelated Track", "Nobody", 259.0)])
    with pytest.raises(SourceError) as exc:
        await acquire(ctx, TabRequest(song_id="s1"), tmp_path)
    assert "no YouTube result confidently matched" in str(exc.value)
    assert "target" not in fake_download  # nothing was downloaded
    assert exc.value.detail["input"]["considered"]


async def test_search_with_no_results_fails_cleanly(
    ctx: SourceContext, tmp_path: Path, fake_download: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_search(monkeypatch, [])
    with pytest.raises(SourceError, match="no YouTube results"):
        await acquire(ctx, TabRequest(song_id="s1"), tmp_path)


async def test_ytdlp_disabled_is_reported(
    ctx: SourceContext, tmp_path: Path, fake_download: dict
) -> None:
    ctx.settings.enable_ytdlp = False
    with pytest.raises(SourceError, match="GUITARISTA_ENABLE_YTDLP=false"):
        await acquire(ctx, TabRequest(song_id="s1", audio_url="https://x/y"), tmp_path)
