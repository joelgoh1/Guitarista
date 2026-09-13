from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.songsterr.client import BASE_URL
from guitarista_api.adapters.spotify import SpotifyTrack
from guitarista_api.db.repo import SongRepo, TabRepo
from guitarista_api.db.repos_noodle import PoolRepo
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.noodle import Evidence
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import Tab, Track
from guitarista_api.services.listening_pool import (
    build_pool,
    merge_tracks,
    score_entry,
)
from guitarista_api.settings import Settings
from guitarista_api.sources.songsterr import SongsterrSource

SEARCH_URL = f"{BASE_URL}/api/songs"


def track(track_id: str, name: str = "Wonderwall", artist: str = "Oasis") -> SpotifyTrack:
    return SpotifyTrack(id=track_id, name=name, artists=[artist], duration_ms=258000)


# --------------------------------------------------------------------------- pure


def test_score_entry_weights_each_channel() -> None:
    assert score_entry(Evidence()) == 0.0
    assert score_entry(Evidence(top_short=0)) == 1.0
    assert score_entry(Evidence(top_medium=0)) == pytest.approx(0.7)
    assert score_entry(Evidence(top_long=0)) == pytest.approx(0.4)
    assert score_entry(Evidence(top_long=25)) == pytest.approx(0.2)
    assert score_entry(Evidence(recent=2)) == pytest.approx(0.2)
    assert score_entry(Evidence(recent=99)) == pytest.approx(0.5)
    assert score_entry(Evidence(liked=True)) == pytest.approx(0.25)


def test_score_entry_sums_and_clamps() -> None:
    assert score_entry(Evidence(top_long=25, liked=True)) == pytest.approx(0.45)
    assert score_entry(Evidence(top_short=0, top_medium=0, recent=5, liked=True)) == 1.0


def test_merge_tracks_accumulates_evidence_and_sorts() -> None:
    a, b, c = track("a"), track("b"), track("c")
    entries = merge_tracks(
        top_short=[b, a],
        top_medium=[a],
        recent=[a, a, c],
        saved=[c],
    )
    by_id = {e.spotify_id: e for e in entries}
    assert by_id["a"].evidence == Evidence(top_short=1, top_medium=0, recent=2)
    assert by_id["b"].evidence == Evidence(top_short=0)
    assert by_id["c"].evidence == Evidence(recent=1, liked=True)
    # scores are derived, and the list comes back best-first
    assert [e.spotify_id for e in entries] == ["a", "b", "c"]
    assert by_id["a"].score == pytest.approx(score_entry(by_id["a"].evidence))


def test_merge_tracks_keeps_metadata_and_dedupes_top_ranks() -> None:
    t = SpotifyTrack(
        id="x", name="Song", artists=["A", "B"], album="LP", artwork_url="http://img", duration_ms=1
    )
    (entry,) = merge_tracks(top_short=[t, t])
    assert entry.title == "Song" and entry.artist == "A, B"
    assert entry.album == "LP" and entry.artwork_url == "http://img" and entry.duration_ms == 1
    assert entry.evidence.top_short == 0  # the first (best) rank wins


def test_merge_tracks_empty() -> None:
    assert merge_tracks() == []


# --------------------------------------------------------------------------- build_pool


class FakeSpotifyUser:
    """Just enough of ``SpotifyUserClient`` for the pool builder."""

    def __init__(self, http: httpx.AsyncClient, **feeds: Any) -> None:
        self.http = http
        self.feeds = feeds
        self.calls: list[str] = []

    async def is_connected(self) -> bool:
        return True

    async def top_tracks(self, time_range: str = "short_term") -> list[SpotifyTrack]:
        self.calls.append(time_range)
        return self._feed(time_range)

    async def recently_played(self) -> list[SpotifyTrack]:
        self.calls.append("recent")
        return self._feed("recent")

    async def saved_tracks(self) -> list[SpotifyTrack]:
        self.calls.append("saved")
        return self._feed("saved")

    def _feed(self, key: str) -> list[SpotifyTrack]:
        value = self.feeds.get(key, [])
        if isinstance(value, Exception):
            raise value
        return list(value)


@pytest.fixture
async def factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'pool.db'}")
    await create_all(engine)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", noodle_refresh_hours=6, _env_file=None)


@pytest.fixture
def songsterr_search(songsterr_fixtures) -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["search"])
        )
        yield router


async def _build(factory, settings, client, sources=None, force=False):
    return await build_pool(
        client=client,  # type: ignore[arg-type]
        session_factory=factory,
        sources=sources if sources is not None else [],
        settings=settings,
        force=force,
    )


async def test_build_pool_merges_and_persists(factory, settings) -> None:
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(
            http,
            short_term=[track("a"), track("b", "Live Forever")],
            medium_term=[track("a")],
            recent=[track("c", "Champagne Supernova")],
            saved=[track("c", "Champagne Supernova")],
        )
        summary = await _build(factory, settings, client)
    assert summary.fetched == 3 and summary.new == 3 and summary.ready == 0
    assert summary.skipped is False and summary.errors == []
    assert sorted(client.calls) == ["long_term", "medium_term", "recent", "saved", "short_term"]
    async with factory() as session:
        stored = await PoolRepo(session).list()
    assert [e.spotify_id for e in stored] == ["a", "b", "c"]
    assert stored[0].evidence.top_short == 0 and stored[0].evidence.top_medium == 0


async def test_build_pool_survives_a_failing_endpoint(factory, settings) -> None:
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(
            http,
            short_term=[track("a")],
            recent=RuntimeError("spotify is down"),
        )
        summary = await _build(factory, settings, client)
    assert summary.fetched == 1
    assert summary.errors and "recent" in summary.errors[0]


async def test_build_pool_skips_while_fresh_unless_forced(factory, settings) -> None:
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(http, short_term=[track("a")])
        assert (await _build(factory, settings, client)).skipped is False
        assert (await _build(factory, settings, client)).skipped is True
        assert (await _build(factory, settings, client, force=True)).skipped is False
    async with factory() as session:
        assert len(await PoolRepo(session).list()) == 1


async def test_build_pool_rebuilds_when_stale(factory, settings) -> None:
    from guitarista_api.db.models import PoolEntryRow

    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(http, short_term=[track("a")])
        await _build(factory, settings, client)
        async with factory() as session:
            row = await session.get(PoolEntryRow, "a")
            assert row is not None
            row.refreshed_at = datetime.now(UTC) - timedelta(hours=48)
            await session.commit()
        assert (await _build(factory, settings, client)).skipped is False


async def test_build_pool_marks_entries_with_an_existing_tab_ready(factory, settings) -> None:
    song = Song(id="song-1", title="Wonderwall", artist="Oasis", spotify_id="a")
    async with factory() as session:
        await SongRepo(session).upsert(song)
        await TabRepo(session).add(
            Tab(
                id="tab-1",
                song_id="song-1",
                title="Wonderwall",
                artist="Oasis",
                source="songsterr",
                tracks=[Track(name="Guitar", tuning=[64, 59, 55, 50, 45, 40], measures=[])],
            )
        )
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(http, short_term=[track("a")])
        summary = await _build(factory, settings, client)
    assert summary.ready == 1
    async with factory() as session:
        entry = await PoolRepo(session).get("a")
    assert entry is not None
    assert entry.status == "ready" and entry.tab_id == "tab-1" and entry.song_id == "song-1"
    assert entry.availability == "available"


async def test_build_pool_probes_songsterr_availability(
    factory, settings, songsterr_search
) -> None:
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(
            http,
            short_term=[track("a"), track("b", "A Song Songsterr Never Heard Of", "Nobody")],
        )
        summary = await _build(factory, settings, client, sources=[SongsterrSource()])
    assert summary.available == 1
    async with factory() as session:
        hit = await PoolRepo(session).get("a")
        miss = await PoolRepo(session).get("b")
    assert hit is not None and hit.availability == "available"
    assert hit.candidate is not None and hit.candidate.source == "songsterr"
    assert hit.candidate.external_id == "2"
    assert miss is not None and miss.availability == "unavailable" and miss.candidate is None
    # an available entry is what the prefetcher picks up next
    async with factory() as session:
        assert [e.spotify_id for e in await PoolRepo(session).next_prefetchable(5)] == ["a"]


async def test_build_pool_preserves_dismissals_across_refreshes(
    factory, settings, songsterr_search
) -> None:
    async with httpx.AsyncClient() as http:
        client = FakeSpotifyUser(http, short_term=[track("a")])
        await _build(factory, settings, client, sources=[SongsterrSource()])
        async with factory() as session:
            assert await PoolRepo(session).dismiss("a")
        await _build(factory, settings, client, sources=[SongsterrSource()], force=True)
    async with factory() as session:
        entry = await PoolRepo(session).get("a")
    assert entry is not None and entry.status == "dismissed"
