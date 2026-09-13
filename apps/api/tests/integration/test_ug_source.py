"""UG tier end to end against recorded HTML fixtures (respx), through the TierRunner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from guitarista_api.adapters.songsterr.client import BASE_URL as SONGSTERR_URL
from guitarista_api.adapters.ultimate_guitar.client import BASE_URL as UG_URL
from guitarista_api.adapters.ultimate_guitar.parse import UGResult
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.domain.song import Song, SongCandidate, SongQuery
from guitarista_api.domain.tab import Tab
from guitarista_api.domain.validate import validate_tab
from guitarista_api.jobs.context import JobContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.services.sources_factory import build_sources
from guitarista_api.services.tier_runner import NoTabFound, TierRunner
from guitarista_api.settings import Settings
from guitarista_api.sources.songsterr import SongsterrSource
from guitarista_api.sources.ultimate_guitar import UltimateGuitarSource, popularity_bonus

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ug"
SEARCH_URL = f"{UG_URL}/search.php"
CHORDS_URL = "https://tabs.ultimate-guitar.com/tab/oasis/wonderwall-chords-6125"
TABS_URL = "https://tabs.ultimate-guitar.com/tab/oasis/wonderwall-tabs-2223387"
CLOUDFLARE_HTML = (
    "<html><head><title>Just a moment...</title></head><body>cf-challenge</body></html>"
)

EMPTY_SEARCH_HTML = (
    "<html><body><div class='js-store' data-content='"
    "{&quot;store&quot;:{&quot;page&quot;:{&quot;data&quot;:{&quot;results&quot;:[]}}}}"
    "'></div></body></html>"
)

SONG = Song(id="raw_1", title="Wonderwall", artist="Oasis")
REQ = TabRequest(song=SongQuery(raw="oasis wonderwall"))


class FakeLLM:
    last_error: str | None = None

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def rank_candidates(self, song: Song, candidates: list[SongCandidate]):
        self.calls.append("rank")
        return list(reversed(candidates))

    async def rewrite_query(self, song: Song, failed: list[str]) -> str | None:
        self.calls.append("rewrite")
        return "wonderwall oasis"

    async def extract_tab_text(self, text: str, tuning: list[int]) -> Tab | None:
        self.calls.append("extract")
        return None


@pytest.fixture
def html() -> dict[str, str]:
    return {
        name: (FIXTURES / f"{name}.html").read_text()
        for name in ("search", "tab_chords_6125", "tab_tabs")
    }


@pytest.fixture
async def make_ctx(tmp_path: Path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    manager = JobManager(factory)
    clients: list[httpx.AsyncClient] = []

    async def _make(llm=None) -> JobContext:
        http = httpx.AsyncClient()
        clients.append(http)
        job = Job(request=REQ)
        return JobContext(
            job, settings=settings, http=http, manager=manager, session_factory=factory, llm=llm
        )

    yield _make
    for c in clients:
        await c.aclose()
    await engine.dispose()


@pytest.fixture
def ug_mock(html) -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.get(f"{SONGSTERR_URL}/api/songs").mock(return_value=httpx.Response(200, json=[]))
        router.get(SEARCH_URL).mock(return_value=httpx.Response(200, text=html["search"]))
        router.get(CHORDS_URL).mock(return_value=httpx.Response(200, text=html["tab_chords_6125"]))
        router.get(TABS_URL).mock(return_value=httpx.Response(200, text=html["tab_tabs"]))
        router.get(url__regex=r"https://tabs\.ultimate-guitar\.com/.*").mock(
            return_value=httpx.Response(200, text=html["tab_chords_6125"])
        )
        yield router


def test_factory_registers_ug_behind_flag(tmp_path: Path) -> None:
    on = build_sources(Settings(data_dir=tmp_path, enable_audio_tier=False, _env_file=None))
    assert [s.name for s in on] == ["songsterr", "ultimate_guitar"]
    off = build_sources(
        Settings(data_dir=tmp_path, enable_ug=False, enable_audio_tier=False, _env_file=None)
    )
    assert [s.name for s in off] == ["songsterr"]


def test_popularity_bonus_is_small_and_monotonic() -> None:
    lo = UGResult(
        id=1, song_name="a", artist_name="b", type="Chords", tab_url="u", rating=3, votes=5
    )
    hi = UGResult(
        id=2, song_name="a", artist_name="b", type="Chords", tab_url="u", rating=4.9, votes=12000
    )
    assert 0 <= popularity_bonus(lo) < popularity_bonus(hi) <= 0.07


async def test_songsterr_fails_then_ug_succeeds(make_ctx, ug_mock: respx.MockRouter) -> None:
    ctx = await make_ctx()
    runner = TierRunner([SongsterrSource(), UltimateGuitarSource()])
    result = await runner.run(REQ, SONG, ctx)
    tab = result.tab
    assert tab.source == "ultimate_guitar" and validate_tab(tab) == []
    assert tab.title == "Wonderwall" and tab.artist == "Oasis" and tab.song_id == SONG.id
    statuses = [(t.tier, t.status) for t in ctx.job.tiers]
    assert statuses == [("songsterr", "failed"), ("ultimate_guitar", "success")]
    detail = ctx.job.tiers[1].detail
    assert detail["llm_used"] is False and detail["deterministic"] is True
    assert detail["picked"]["type"] in {"Tabs", "Chords"} and detail["candidates"]
    assert detail["results"]["usable"] < detail["results"]["total"]
    assert ug_mock.get(SEARCH_URL) is not None
    search_calls = [c for c in ug_mock.calls if c.request.url.path == "/search.php"]
    assert search_calls and search_calls[0].request.url.params["value"] == "oasis wonderwall"
    assert search_calls[0].request.url.params["search_type"] == "title"


async def test_tabs_preferred_over_chords_and_page_fetched(make_ctx, ug_mock) -> None:
    ctx = await make_ctx()
    result = await UltimateGuitarSource().fetch(REQ, SONG, ctx)
    # the fixture's top-scored Tabs candidate is #2223387; the recorded tabs page is used
    picked = result.detail["picked"]
    assert picked["type"] == "Tabs" and picked["url"] == TABS_URL
    assert result.tab.source_ref == "ug:2223387" and result.tab.tracks[0].capo == 2
    assert "notes" in (result.message or "")


async def test_ug_with_llm_marks_llm_used(make_ctx, ug_mock) -> None:
    llm = FakeLLM()
    ctx = await make_ctx(llm=llm)
    ug_mock.get(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(200, text=EMPTY_SEARCH_HTML),
            httpx.Response(200, text=EMPTY_SEARCH_HTML),
            httpx.Response(200, text=EMPTY_SEARCH_HTML),
            httpx.Response(200, text=(FIXTURES / "search.html").read_text()),
        ]
    )
    result = await UltimateGuitarSource().fetch(REQ, SONG, ctx)
    assert "rewrite" in llm.calls
    assert result.detail["llm_used"] is True
    assert result.detail["rewritten_query"] == "wonderwall oasis"
    assert result.detail["queries"][-1] == "wonderwall oasis"


async def test_cloudflare_block_fails_tier_with_message(make_ctx, ug_mock) -> None:
    ctx = await make_ctx()
    ug_mock.get(SEARCH_URL).mock(return_value=httpx.Response(403, text=CLOUDFLARE_HTML))
    with pytest.raises(NoTabFound) as exc:
        await TierRunner([UltimateGuitarSource()]).run(REQ, SONG, ctx)
    entry = exc.value.tiers[0]
    assert entry.status == "failed" and entry.message == "Ultimate Guitar blocked the request"


async def test_no_usable_results_fails(make_ctx, ug_mock) -> None:
    ctx = await make_ctx()
    ug_mock.get(SEARCH_URL).mock(return_value=httpx.Response(200, text=EMPTY_SEARCH_HTML))
    with pytest.raises(NoTabFound) as exc:
        await TierRunner([UltimateGuitarSource()]).run(REQ, SONG, ctx)
    assert "no Tabs/Chords results" in (exc.value.tiers[0].message or "")


async def test_disabled_flag_skips(make_ctx, tmp_path: Path) -> None:
    ctx = await make_ctx()
    ctx.settings = Settings(data_dir=tmp_path, enable_ug=False, _env_file=None)
    ok, reason = UltimateGuitarSource().can_handle(REQ, SONG, ctx)
    assert ok is False and "GUITARISTA_ENABLE_UG" in (reason or "")
