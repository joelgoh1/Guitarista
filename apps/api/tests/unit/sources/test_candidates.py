"""``candidates()`` per source on recorded fixtures, plus ``exclude`` / ``candidate`` handling
through the ``TierRunner`` (respx, no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from guitarista_api.adapters.songsterr.client import BASE_URL as SONGSTERR_URL
from guitarista_api.adapters.songsterr.client import CDN_URL
from guitarista_api.adapters.ultimate_guitar.client import BASE_URL as UG_URL
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import CandidateRef, Job, TabRequest
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.jobs.context import JobContext, SourceContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.services.candidates import collect_candidates
from guitarista_api.services.tier_runner import NoTabFound, TierRunner
from guitarista_api.settings import Settings
from guitarista_api.sources.audio import AudioSource
from guitarista_api.sources.base import SourceError
from guitarista_api.sources.songsterr import SongsterrSource, track_summary
from guitarista_api.sources.ultimate_guitar import UltimateGuitarSource

UG_FIXTURES = Path(__file__).parents[2] / "fixtures" / "ug"
SEARCH_URL = f"{SONGSTERR_URL}/api/songs"
UG_SEARCH_URL = f"{UG_URL}/search.php"
UG_TABS_URL = "https://tabs.ultimate-guitar.com/tab/oasis/wonderwall-tabs-2223387"
UG_TABS_BY_ID_URL = "https://tabs.ultimate-guitar.com/tab/2223387"
IMAGE = "v0-3-2-hmpMBN-NNIVq9p59"
ALL_SONGSTERR_IDS = [
    "2", "402823", "385188", "1566116", "454846", "231809", "446613", "385164", "385163",
    "1617145",
]  # fmt: skip

SONG = Song(id="s1", title="Wonderwall", artist="Oasis")


def ref(source: str, external_id: str) -> CandidateRef:
    return CandidateRef(source=source, external_id=external_id)  # type: ignore[arg-type]


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[dict]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    async with httpx.AsyncClient() as http:
        ctx = SourceContext(settings=settings, http=http, session_factory=factory)
        job = Job(request=TabRequest(song=SongQuery(raw="x")))
        jctx = JobContext(
            job, settings=settings, http=http, manager=JobManager(factory), session_factory=factory
        )
        yield {"ctx": ctx, "jctx": jctx, "settings": settings, "factory": factory}
    await engine.dispose()


@pytest.fixture
def mocks(songsterr_fixtures) -> AsyncIterator[respx.MockRouter]:
    meta = songsterr_fixtures["meta"]
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["search"])
        )
        for song_id in ALL_SONGSTERR_IDS:
            router.get(f"{SONGSTERR_URL}/api/meta/{song_id}").mock(
                return_value=httpx.Response(200, json={**meta, "songId": int(song_id)})
            )
            for idx in (3, 6):
                router.get(f"{CDN_URL}/{song_id}/{meta['revisionId']}/{IMAGE}/{idx}.json").mock(
                    return_value=httpx.Response(200, json=songsterr_fixtures[f"track_{idx}"])
                )
        router.get(url__regex=rf"{CDN_URL}/.*").mock(return_value=httpx.Response(404))
        router.get(UG_SEARCH_URL).mock(
            return_value=httpx.Response(200, text=(UG_FIXTURES / "search.html").read_text())
        )
        tabs_html = (UG_FIXTURES / "tab_tabs.html").read_text()
        router.get(UG_TABS_URL).mock(return_value=httpx.Response(200, text=tabs_html))
        router.get(UG_TABS_BY_ID_URL).mock(return_value=httpx.Response(200, text=tabs_html))
        router.get(url__regex=r"https://tabs\.ultimate-guitar\.com/.*").mock(
            return_value=httpx.Response(
                200, text=(UG_FIXTURES / "tab_chords_6125.html").read_text()
            )
        )
        yield router


def _calls(router: respx.MockRouter, path: str) -> list:
    return [c for c in router.calls if c.request.url.path == path]


# ----------------------------------------------------------------- candidates()


async def test_songsterr_candidates_ranked_with_track_summary(env, mocks) -> None:
    found = await SongsterrSource().candidates(SONG, env["ctx"], limit=5)
    assert len(found) == 5
    assert [c.external_id for c in found[:2]] == ["2", "402823"]
    top = found[0]
    assert top.source == "songsterr" and top.score == 1.0 and top.available is True
    assert top.title == "Wonderwall" and top.artist == "Oasis"
    assert top.track_count == 14 and top.kind and top.kind.startswith("guitar x")
    assert top.url == "https://www.songsterr.com/a/wsa/oasis-wonderwall-tab-s2"
    assert top.tab_id is None and top.rating is None and top.votes is None
    assert all(a.score >= b.score for a, b in zip(found, found[1:], strict=False))
    # nothing but the search endpoint was hit
    assert {c.request.url.path for c in mocks.calls} == {"/api/songs"}


async def test_ug_candidates_only_tabs_and_chords(env, mocks) -> None:
    found = await UltimateGuitarSource().candidates(SONG, env["ctx"], limit=50)
    assert found and {c.kind for c in found} <= {"Tabs", "Chords"}
    assert all(c.source == "ultimate_guitar" for c in found)
    assert len(found) == 21  # every Tabs/Chords row in the fixture; Pro/Bass/Video dropped
    best = found[0]
    assert best.url and best.url.startswith("https://tabs.ultimate-guitar.com/tab/oasis/")
    assert best.rating is not None and best.votes is not None and 0 < best.score <= 1
    assert all(a.score >= b.score for a, b in zip(found, found[1:], strict=False))
    assert len(await UltimateGuitarSource().candidates(SONG, env["ctx"], limit=3)) == 3


async def test_audio_candidate_reports_availability(env) -> None:
    found = await AudioSource().candidates(SONG, env["ctx"], limit=10)
    assert len(found) == 1
    audio = found[0]
    assert audio.source == "audio" and audio.external_id == "audio" and audio.score == 0.5
    assert audio.available is False and "yt-dlp fetching is disabled" in (audio.reason or "")
    assert audio.kind == "YouTube (search)"


async def test_disabled_sources_yield_nothing(env, tmp_path: Path) -> None:
    ctx = env["ctx"]
    ctx.settings = Settings(
        data_dir=tmp_path, enable_songsterr=False, enable_ug=False, _env_file=None
    )
    assert await SongsterrSource().candidates(SONG, ctx, limit=5) == []
    assert await UltimateGuitarSource().candidates(SONG, ctx, limit=5) == []


async def test_collect_candidates_merges_in_source_order_with_warnings(env, mocks) -> None:
    mocks.get(UG_SEARCH_URL).mock(return_value=httpx.Response(500))
    sources = [AudioSource(), UltimateGuitarSource(), SongsterrSource()]  # deliberately shuffled
    out = await collect_candidates(
        SONG, sources, env["ctx"], timeouts={"songsterr": 5, "ultimate_guitar": 5}, limit=3
    )
    assert out.song_id == "s1"
    assert [c.source for c in out.candidates] == ["songsterr"] * 3 + ["audio"]
    assert out.warnings and out.warnings[0].startswith("ultimate_guitar:")


async def test_collect_candidates_timeout_becomes_warning(env, mocks) -> None:
    class Slow(SongsterrSource):
        async def candidates(self, song, ctx, *, limit):
            import asyncio

            await asyncio.sleep(5)
            return []

    out = await collect_candidates(
        SONG, [Slow()], env["ctx"], timeouts={"songsterr": 0.05}, limit=3
    )
    assert out.candidates == [] and out.warnings == ["songsterr: timed out after 0.05s"]


def test_track_summary_counts_by_hash_prefix(songsterr_fixtures) -> None:
    from guitarista_api.adapters.songsterr.schema import SearchResult

    result = SearchResult.model_validate(songsterr_fixtures["search"][0])
    assert track_summary(result) == "guitar x4, drums x4, other x3, vocals x2, bass"
    assert track_summary(SearchResult(songId=1)) is None


# ----------------------------------------------------------------- exclude / candidate


async def test_exclude_walks_to_second_songsterr_candidate(env, mocks) -> None:
    jctx = env["jctx"]
    request = TabRequest(song_id="s1", exclude=[ref("songsterr", "2")])
    result = await TierRunner([SongsterrSource(), UltimateGuitarSource()]).run(request, SONG, jctx)
    assert result.tab.source_ref and result.tab.source_ref.startswith("songsterr:402823:")
    entry = jctx.job.tiers[0]
    assert entry.status == "success" and entry.detail["excluded"] == 1
    assert entry.detail["picked"]["songId"] == 402823
    assert _calls(mocks, "/api/meta/2") == [] and _calls(mocks, "/api/meta/402823")


async def test_all_songsterr_excluded_falls_to_ug(env, mocks) -> None:
    jctx = env["jctx"]
    request = TabRequest(song_id="s1", exclude=[ref("songsterr", i) for i in ALL_SONGSTERR_IDS])
    result = await TierRunner([SongsterrSource(), UltimateGuitarSource()]).run(request, SONG, jctx)
    assert result.tab.source == "ultimate_guitar"
    ss, ug = jctx.job.tiers
    assert ss.status == "failed" and ss.message == "all 10 candidates excluded"
    assert ss.detail["excluded"] == 10 and ug.status == "success" and ug.detail["excluded"] == 0
    assert _calls(mocks, "/api/meta/2") == []


async def test_ug_exclude_skips_to_next_tab_id(env, mocks) -> None:
    ctx = env["ctx"]
    ranked = await UltimateGuitarSource().candidates(SONG, ctx, limit=2)
    request = TabRequest(song_id="s1", exclude=[ref("ultimate_guitar", ranked[0].external_id)])
    result = await UltimateGuitarSource().fetch(request, SONG, ctx)
    assert result.detail["excluded"] == 1
    assert result.detail["picked"]["id"] == int(ranked[1].external_id)
    everything = await UltimateGuitarSource().candidates(SONG, ctx, limit=50)
    request = TabRequest(exclude=[ref("ultimate_guitar", c.external_id) for c in everything])
    with pytest.raises(SourceError, match="all 21 candidates excluded"):
        await UltimateGuitarSource().fetch(request, SONG, ctx)


async def test_audio_excluded_fails_and_chain_continues(env) -> None:
    request = TabRequest(song_id="s1", exclude=[ref("audio", "audio")])
    with pytest.raises(SourceError, match="all 1 candidates excluded"):
        await AudioSource().fetch(request, SONG, env["ctx"])


async def test_candidate_targets_songsterr_without_search(env, mocks) -> None:
    jctx = env["jctx"]
    request = TabRequest(song_id="s1", candidate=ref("songsterr", "402823"))
    sources = [SongsterrSource(), UltimateGuitarSource(), AudioSource()]
    result = await TierRunner(sources).run(request, SONG, jctx)
    assert result.tab.source_ref and result.tab.source_ref.startswith("songsterr:402823:")
    assert [t.tier for t in jctx.job.tiers] == ["songsterr"]  # only the targeted source ran
    picked = jctx.job.tiers[0].detail["picked"]
    assert picked["songId"] == 402823 and picked["targeted"] is True
    assert picked["title"] == "Wonderwall" and "candidates" not in jctx.job.tiers[0].detail
    assert _calls(mocks, "/api/songs") == []


async def test_candidate_targets_ug_page_by_id(env, mocks) -> None:
    jctx = env["jctx"]
    request = TabRequest(song_id="s1", candidate=ref("ultimate_guitar", "2223387"))
    result = await TierRunner([SongsterrSource(), UltimateGuitarSource()]).run(request, SONG, jctx)
    assert result.tab.source_ref == "ug:2223387"
    assert [t.tier for t in jctx.job.tiers] == ["ultimate_guitar"]
    assert jctx.job.tiers[0].detail["picked"]["targeted"] is True
    assert _calls(mocks, "/search.php") == [] and _calls(mocks, "/api/songs") == []


async def test_candidate_for_missing_source_is_no_tab_found(env, mocks) -> None:
    request = TabRequest(song_id="s1", candidate=ref("audio", "audio"))
    with pytest.raises(NoTabFound, match="no tab sources available"):
        await TierRunner([SongsterrSource()]).run(request, SONG, env["jctx"])


def test_tab_request_helpers() -> None:
    req = TabRequest(
        song_id="s1",
        candidate=ref("songsterr", "7"),
        exclude=[ref("songsterr", "1"), ref("ultimate_guitar", "9"), ref("songsterr", "2")],
    )
    assert req.has_song() and req.excluded_ids("songsterr") == {"1", "2"}
    assert req.targeted_id("songsterr") == "7" and req.targeted_id("audio") is None
    assert not TabRequest().has_song() and TabRequest(song=SongQuery(raw="x")).has_song()
