from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from guitarista_api.adapters.spotify_user import code_challenge_for
from guitarista_api.main import create_app
from guitarista_api.settings import Settings

TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"
REDIRECT_URI = "http://127.0.0.1:8000/api/v1/spotify/callback"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        spotify_client_id="cid",
        spotify_redirect_uri=REDIRECT_URI,
        web_base_url="http://localhost:3000",
        enable_audio_tier=False,
        _env_file=None,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_connect_disconnect_round_trip(app: FastAPI, client: AsyncClient) -> None:
    assert (await client.get("/api/v1/spotify/status")).json() == {
        "connected": False,
        "display_name": None,
        "spotify_user_id": None,
        "scopes": [],
        "expires_at": None,
        "configured": True,
    }
    health = (await client.get("/api/v1/health")).json()
    assert health["features"]["spotify_user"] is True
    assert health["features"]["spotify_connected"] is False

    r = await client.get("/api/v1/spotify/login")
    assert r.status_code == 200
    url = urlparse(r.json()["authorize_url"])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.spotify.com" and url.path == "/authorize"
    assert params["response_type"] == "code" and params["code_challenge_method"] == "S256"
    assert params["client_id"] == "cid" and params["redirect_uri"] == REDIRECT_URI
    assert "user-top-read" in params["scope"]

    state = params["state"]
    verifier, _expiry = app.state.spotify_pkce[state]
    assert code_challenge_for(verifier) == params["code_challenge"]

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        token = router.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "scope": "user-top-read user-read-recently-played",
                },
            )
        )
        router.get(ME_URL).mock(
            return_value=httpx.Response(200, json={"id": "joel", "display_name": "Joel"})
        )
        r = await client.get(
            "/api/v1/spotify/callback", params={"code": "the-code", "state": state}
        )
    assert r.status_code == 303
    assert r.headers["location"] == "http://localhost:3000/settings?spotify=connected"
    sent = dict(httpx.QueryParams(token.calls[0].request.content.decode()))
    assert sent["grant_type"] == "authorization_code" and sent["code_verifier"] == verifier
    assert state not in app.state.spotify_pkce  # single use

    status = (await client.get("/api/v1/spotify/status")).json()
    assert status["connected"] is True and status["display_name"] == "Joel"
    assert status["spotify_user_id"] == "joel" and status["expires_at"]
    assert status["scopes"] == ["user-top-read", "user-read-recently-played"]
    assert (await client.get("/api/v1/health")).json()["features"]["spotify_connected"] is True

    r = await client.delete("/api/v1/spotify/auth")
    assert r.status_code == 204
    assert (await client.get("/api/v1/spotify/status")).json()["connected"] is False
    assert (await client.get("/api/v1/health")).json()["features"]["spotify_connected"] is False
    # deleting again is a no-op
    assert (await client.delete("/api/v1/spotify/auth")).status_code == 204


async def test_callback_errors_redirect_with_reason(client: AsyncClient) -> None:
    r = await client.get("/api/v1/spotify/callback", params={"code": "x", "state": "unknown"})
    assert r.status_code == 303
    assert (
        r.headers["location"] == "http://localhost:3000/settings?spotify=error&reason=invalid_state"
    )

    r = await client.get("/api/v1/spotify/callback", params={"error": "access_denied"})
    assert r.headers["location"].endswith("?spotify=error&reason=access_denied")


async def test_callback_reports_a_rejected_code(app: FastAPI, client: AsyncClient) -> None:
    state = (await client.get("/api/v1/spotify/login")).json()["authorize_url"]
    state = parse_qs(urlparse(state).query)["state"][0]
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid"}))
        r = await client.get("/api/v1/spotify/callback", params={"code": "bad", "state": state})
    assert r.headers["location"].endswith("?spotify=error&reason=exchange_failed")
    assert (await client.get("/api/v1/spotify/status")).json()["connected"] is False


async def test_prefetcher_hooks_are_called_when_present(app: FastAPI, client: AsyncClient) -> None:
    class FakePrefetcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def start(self) -> None:
            self.calls.append("start")

        async def stop(self) -> None:
            self.calls.append("stop")

    prefetcher = FakePrefetcher()
    app.state.noodle_prefetcher = prefetcher
    state = (await client.get("/api/v1/spotify/login")).json()["authorize_url"]
    state = parse_qs(urlparse(state).query)["state"][0]
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3600}
            )
        )
        router.get(ME_URL).mock(return_value=httpx.Response(200, json={"id": "joel"}))
        await client.get("/api/v1/spotify/callback", params={"code": "c", "state": state})
    await client.delete("/api/v1/spotify/auth")
    assert prefetcher.calls == ["start", "stop"]


async def test_login_requires_a_client_id(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data2",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test2.db'}",
        spotify_client_id="",
        enable_audio_tier=False,
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/spotify/login")
            assert r.status_code == 409
            assert r.headers["content-type"].startswith("application/problem+json")
            health = (await c.get("/api/v1/health")).json()
            assert health["features"]["spotify_user"] is False
            assert (await c.get("/api/v1/spotify/status")).json()["configured"] is False
