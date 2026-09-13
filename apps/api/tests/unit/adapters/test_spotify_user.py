from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.spotify_user import (
    SpotifyNotConnected,
    SpotifyUserClient,
    build_authorize_url,
    code_challenge_for,
    exchange_code,
    make_code_verifier,
)
from guitarista_api.db.repos_noodle import SpotifyAuthRepo
from guitarista_api.db.session import create_all, make_engine, make_session_factory

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"


def track(track_id: str, name: str = "Song") -> dict:
    return {
        "id": track_id,
        "name": name,
        "artists": [{"name": "Oasis"}],
        "album": {"name": "Album", "images": [{"url": "http://img"}]},
        "duration_ms": 200000,
    }


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'noodle.db'}")
    await create_all(engine)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def connected(session_factory) -> async_sessionmaker[AsyncSession]:
    async with session_factory() as session:
        await SpotifyAuthRepo(session).upsert(refresh_token="refresh-1")
    return session_factory


def test_pkce_challenge_is_url_safe_b64_sha256() -> None:
    verifier = make_code_verifier()
    assert 43 <= len(verifier) <= 128
    challenge = code_challenge_for(verifier)
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge
    url = build_authorize_url(
        client_id="cid",
        redirect_uri="http://127.0.0.1:8000/api/v1/spotify/callback",
        state="st",
        code_verifier=verifier,
    )
    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "code_challenge_method=S256" in url and f"code_challenge={challenge}" in url
    assert "client_id=cid" in url and "state=st" in url


@respx.mock
async def test_refresh_uses_client_id_and_persists_rotated_token(connected) -> None:
    token = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
                "scope": "user-top-read user-library-read",
            },
        )
    )
    top = respx.get(f"{API}/me/top/tracks").mock(
        return_value=httpx.Response(200, json={"items": [track("a"), track("b")]})
    )
    async with httpx.AsyncClient() as http:
        client = SpotifyUserClient(http, "cid", connected)
        assert await client.is_connected() is True
        tracks = await client.top_tracks("medium_term")
        await client.top_tracks("long_term")  # cached token, no second refresh

    assert token.call_count == 1
    body = dict(httpx.QueryParams(token.calls[0].request.content.decode()))
    assert body == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "client_id": "cid",
    }
    assert top.calls[0].request.url.params["time_range"] == "medium_term"
    assert top.calls[0].request.headers["Authorization"] == "Bearer access-1"
    assert [t.id for t in tracks] == ["a", "b"]

    async with connected() as session:
        row = await SpotifyAuthRepo(session).get()
    assert row is not None
    assert row.refresh_token == "refresh-2"  # rotated token persisted
    assert row.access_token == "access-1" and row.expires_at is not None
    assert row.scope == "user-top-read user-library-read"


@respx.mock
async def test_refresh_keeps_old_token_when_response_omits_it(connected) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    respx.get(f"{API}/me").mock(return_value=httpx.Response(200, json={"id": "joel"}))
    async with httpx.AsyncClient() as http:
        assert (await SpotifyUserClient(http, "cid", connected).me())["id"] == "joel"
    async with connected() as session:
        row = await SpotifyAuthRepo(session).get()
    assert row is not None and row.refresh_token == "refresh-1"


@respx.mock
async def test_not_connected_raises(session_factory) -> None:
    async with httpx.AsyncClient() as http:
        client = SpotifyUserClient(http, "cid", session_factory)
        assert await client.is_connected() is False
        with pytest.raises(SpotifyNotConnected):
            await client.top_tracks()


@respx.mock
async def test_recently_played_and_saved_tracks_unwrap_item_track(connected) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    respx.get(f"{API}/me/player/recently-played").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"track": track("r1"), "played_at": "2026-01-01T00:00:00Z"},
                    {"track": {"id": None, "name": "local file"}},  # skipped
                ]
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = SpotifyUserClient(http, "cid", connected)
        recent = await client.recently_played()
    assert [t.id for t in recent] == ["r1"]


@respx.mock
async def test_saved_tracks_paginates_until_short_page(connected) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    pages = [
        {"items": [{"track": track(f"p0-{i}")} for i in range(50)], "next": "more"},
        {"items": [{"track": track(f"p1-{i}")} for i in range(50)], "next": "more"},
        {"items": [{"track": track("p2-0")}], "next": None},
    ]
    saved = respx.get(f"{API}/me/tracks").mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )
    async with httpx.AsyncClient() as http:
        tracks = await SpotifyUserClient(http, "cid", connected).saved_tracks(pages=3)
    assert saved.call_count == 3
    assert [c.request.url.params["offset"] for c in saved.calls] == ["0", "50", "100"]
    assert len(tracks) == 101 and tracks[-1].id == "p2-0"


@respx.mock
async def test_saved_tracks_stops_early_on_short_page(connected) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    saved = respx.get(f"{API}/me/tracks").mock(
        return_value=httpx.Response(200, json={"items": [{"track": track("x")}], "next": None})
    )
    async with httpx.AsyncClient() as http:
        tracks = await SpotifyUserClient(http, "cid", connected).saved_tracks(pages=3)
    assert saved.call_count == 1 and [t.id for t in tracks] == ["x"]


@respx.mock
async def test_429_honours_retry_after_then_succeeds(connected, monkeypatch) -> None:
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("guitarista_api.adapters.spotify_user.asyncio.sleep", fake_sleep)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    route = respx.get(f"{API}/me/top/tracks").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"items": [track("a")]}),
        ]
    )
    async with httpx.AsyncClient() as http:
        tracks = await SpotifyUserClient(http, "cid", connected).top_tracks()
    assert route.call_count == 2 and slept == [3.0] and [t.id for t in tracks] == ["a"]


@respx.mock
async def test_429_retry_sleep_is_bounded(connected, monkeypatch) -> None:
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("guitarista_api.adapters.spotify_user.asyncio.sleep", fake_sleep)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
    )
    respx.get(f"{API}/me/top/tracks").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "900"})
    )
    async with httpx.AsyncClient() as http:
        client = SpotifyUserClient(http, "cid", connected, max_retries=2, max_retry_sleep=10)
        with pytest.raises(Exception) as exc:
            await client.top_tracks()
    assert getattr(exc.value, "status", None) == 429
    assert slept == [10.0, 10.0]  # never sleeps for the full 15 minutes


@respx.mock
async def test_exchange_code_posts_verifier_and_requires_refresh_token() -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3600}
        )
    )
    async with httpx.AsyncClient() as http:
        body = await exchange_code(
            http,
            client_id="cid",
            code="the-code",
            redirect_uri="http://127.0.0.1:8000/api/v1/spotify/callback",
            code_verifier="verifier",
        )
    assert body["refresh_token"] == "r"
    sent = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
    assert sent["grant_type"] == "authorization_code" and sent["code_verifier"] == "verifier"
    assert sent["code"] == "the-code" and sent["client_id"] == "cid"
