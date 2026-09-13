from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.spotify import SpotifyClient
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.song import SongQuery
from guitarista_api.services.song_resolver import (
    SongResolveError,
    SongResolver,
    parse_raw_query,
)
from tests.unit.adapters.test_spotify import TRACK_ID, TRACK_JSON


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")
    await create_all(engine)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Oasis - Wonderwall", ("Wonderwall", "Oasis")),
        ("Wonderwall by Oasis", ("Wonderwall", "Oasis")),
        ("oasis wonderwall", ("oasis wonderwall", "")),
        ("Oasis – Wonderwall (Remastered 2014)", ("Wonderwall", "Oasis")),
    ],
)
def test_parse_raw_query(raw: str, expected: tuple[str, str]) -> None:
    assert parse_raw_query(raw) == expected


async def test_raw_path_and_dedupe(session_factory) -> None:
    resolver = SongResolver(session_factory, spotify=None)
    a = await resolver.resolve(SongQuery(raw="Oasis - Wonderwall"))
    b = await resolver.resolve(SongQuery(title="Wonderwall - Remastered 2014", artist="oasis"))
    assert a.id == b.id and a.id.startswith("raw_")
    assert a.title == "Wonderwall" and a.artist == "Oasis"
    assert a.normalized_query == "oasis wonderwall"
    # a plain string normalizes to the same key and reuses the existing song
    c = await resolver.resolve(SongQuery(raw="oasis wonderwall"))
    assert c.id == a.id and c.artist == "Oasis"
    d = await resolver.resolve(SongQuery(raw="champagne supernova"))
    assert d.artist == "" and d.title == "champagne supernova" and d.id != a.id


async def test_empty_and_spotify_link_without_credentials(session_factory) -> None:
    resolver = SongResolver(session_factory, spotify=None)
    with pytest.raises(SongResolveError):
        await resolver.resolve(SongQuery())
    with pytest.raises(SongResolveError, match="Spotify links need"):
        await resolver.resolve(SongQuery(spotify_url=f"https://open.spotify.com/track/{TRACK_ID}"))
    with pytest.raises(SongResolveError, match="does not look like"):
        await resolver.resolve(SongQuery(spotify_url="https://example.com/x"))


@respx.mock
async def test_spotify_path_and_dedupe_by_spotify_id(session_factory) -> None:
    respx.post("https://accounts.spotify.com/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    respx.get(f"https://api.spotify.com/v1/tracks/{TRACK_ID}").mock(
        return_value=httpx.Response(200, json=TRACK_JSON)
    )
    respx.get("https://api.spotify.com/v1/search").mock(
        return_value=httpx.Response(200, json={"tracks": {"items": [TRACK_JSON]}})
    )
    async with httpx.AsyncClient() as http:
        resolver = SongResolver(session_factory, SpotifyClient(http, "id", "s"))
        via_link = await resolver.resolve(SongQuery(raw=f"spotify:track:{TRACK_ID}"))
        via_text = await resolver.resolve(SongQuery(raw="oasis wonderwall"))
    assert via_link.spotify_id == TRACK_ID and via_link.id == via_text.id
    assert via_text.title == "Wonderwall"


@respx.mock
async def test_spotify_search_failure_falls_back_to_raw(session_factory) -> None:
    respx.post("https://accounts.spotify.com/api/token").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        resolver = SongResolver(session_factory, SpotifyClient(http, "id", "s"))
        song = await resolver.resolve(SongQuery(raw="Oasis - Wonderwall"))
    assert song.spotify_id is None and song.title == "Wonderwall"
