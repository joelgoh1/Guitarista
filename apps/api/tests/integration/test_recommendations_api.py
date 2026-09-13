from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from guitarista_api.adapters.songsterr.client import BASE_URL
from guitarista_api.db.repos_noodle import SpotifyAuthRepo
from guitarista_api.main import create_app
from guitarista_api.settings import Settings

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SEARCH_URL = f"{BASE_URL}/api/songs"


def spotify_track(track_id: str, name: str, artist: str = "Oasis") -> dict[str, Any]:
    return {
        "id": track_id,
        "name": name,
        "artists": [{"name": artist}],
        "album": {"name": "(What's the Story) Morning Glory?", "images": [{"url": "http://img"}]},
        "duration_ms": 258000,
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        spotify_client_id="cid",
        enable_ug=False,
        enable_audio_tier=False,
        noodle_enabled=False,  # the prefetcher has its own tests; keep the loop out of this one
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


@pytest.fixture
def spotify_mock(songsterr_fixtures) -> AsyncIterator[respx.MockRouter]:
    """A connected account with a small history, plus the recorded Songsterr search."""
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
            )
        )
        router.get(f"{API}/me/top/tracks").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        spotify_track("a", "Wonderwall"),
                        spotify_track("b", "Nobody Has This Tab", "Some Nobody"),
                    ]
                },
            )
        )
        router.get(f"{API}/me/player/recently-played").mock(
            return_value=httpx.Response(
                200, json={"items": [{"track": spotify_track("a", "Wonderwall")}]}
            )
        )
        router.get(f"{API}/me/tracks").mock(
            return_value=httpx.Response(
                200, json={"items": [{"track": spotify_track("a", "Wonderwall")}], "next": None}
            )
        )
        router.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["search"])
        )
        yield router


async def connect(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        await SpotifyAuthRepo(session).upsert(refresh_token="rt", display_name="Joel")


# --------------------------------------------------------------------------- disconnected


async def test_every_route_is_409_without_a_grant(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/recommendations")).status_code == 409
    assert (await client.post("/api/v1/recommendations/refresh")).status_code == 409
    assert (await client.post("/api/v1/recommendations/a/dismiss")).status_code == 409
    r = await client.get("/api/v1/recommendations/surprise")
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "not connected" in r.json()["detail"]


# --------------------------------------------------------------------------- connected


async def test_refresh_list_surprise_dismiss(
    app: FastAPI, client: AsyncClient, spotify_mock
) -> None:
    await connect(app)

    r = await client.post("/api/v1/recommendations/refresh")
    assert r.status_code == 202
    summary = r.json()
    assert summary["fetched"] == 2 and summary["new"] == 2 and summary["skipped"] is False
    assert summary["available"] == 1  # only Wonderwall is on Songsterr

    r = await client.get("/api/v1/recommendations")
    assert r.status_code == 200
    entries = r.json()
    assert [e["spotify_id"] for e in entries] == ["a"]  # "b" is unavailable and filtered out
    entry = entries[0]
    assert entry["title"] == "Wonderwall" and entry["artist"] == "Oasis"
    assert entry["artwork_url"] == "http://img" and entry["score"] > 0
    assert entry["evidence"]["top_short"] == 0 and entry["evidence"]["liked"] is True
    assert entry["candidate"]["source"] == "songsterr"
    assert entry["availability"] == "available" and entry["tab_id"] is None

    r = await client.get("/api/v1/recommendations/surprise")
    assert r.status_code == 200
    pick = r.json()
    assert pick["entry"]["spotify_id"] == "a" and pick["tab_id"] is None
    assert pick["reason"] == "needs generating"

    assert (await client.post("/api/v1/recommendations/a/dismiss")).status_code == 204
    assert (await client.get("/api/v1/recommendations")).json() == []
    assert (await client.get("/api/v1/recommendations/surprise")).status_code == 404
    assert (await client.post("/api/v1/recommendations/zzz/dismiss")).status_code == 404


async def test_refresh_is_forced_and_limit_applies(
    app: FastAPI, client: AsyncClient, spotify_mock
) -> None:
    await connect(app)
    assert (await client.post("/api/v1/recommendations/refresh")).json()["skipped"] is False
    # a second refresh right after is still honoured (the endpoint forces it)
    second = (await client.post("/api/v1/recommendations/refresh")).json()
    assert second["skipped"] is False and second["new"] == 0
    r = await client.get("/api/v1/recommendations", params={"limit": 1})
    assert len(r.json()) == 1
