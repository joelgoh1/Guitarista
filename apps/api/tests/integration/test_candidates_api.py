"""``POST /songs/{id}/candidates`` and the ``song_id`` / ``exclude`` / ``candidate`` job fields."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from guitarista_api.adapters.songsterr.client import BASE_URL, CDN_URL
from guitarista_api.adapters.ultimate_guitar.client import BASE_URL as UG_URL
from guitarista_api.db.repo import JobRepo
from guitarista_api.main import create_app
from guitarista_api.settings import Settings

UG_FIXTURES = Path(__file__).parents[1] / "fixtures" / "ug"
IMAGE = "v0-3-2-hmpMBN-NNIVq9p59"
UG_TABS_HTML = (UG_FIXTURES / "tab_tabs.html").read_text()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_ytdlp=False,
        _env_file=None,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def mocks(songsterr_fixtures) -> AsyncIterator[respx.MockRouter]:
    meta = songsterr_fixtures["meta"]
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.get(f"{BASE_URL}/api/songs").mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["search"])
        )
        for song_id in (2, 402823):
            router.get(f"{BASE_URL}/api/meta/{song_id}").mock(
                return_value=httpx.Response(200, json={**meta, "songId": song_id})
            )
            for idx in (3, 6):
                router.get(f"{CDN_URL}/{song_id}/{meta['revisionId']}/{IMAGE}/{idx}.json").mock(
                    return_value=httpx.Response(200, json=songsterr_fixtures[f"track_{idx}"])
                )
        router.get(url__regex=rf"{CDN_URL}/.*").mock(return_value=httpx.Response(404))
        router.get(f"{UG_URL}/search.php").mock(
            return_value=httpx.Response(200, text=(UG_FIXTURES / "search.html").read_text())
        )
        router.get(url__regex=r"https://tabs\.ultimate-guitar\.com/tab/.*2223387$").mock(
            return_value=httpx.Response(200, text=UG_TABS_HTML)
        )
        yield router


async def poll(client: AsyncClient, job_id: str, max_wait: float = 10) -> dict:
    async with asyncio.timeout(max_wait):
        while True:
            job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if job["status"] in {"done", "failed", "cancelled"}:
                return job
            await asyncio.sleep(0.02)


def tier(job: dict, name: str) -> dict:
    return next(t for t in job["tiers"] if t["tier"] == name)


async def test_browse_then_exclude_then_target(app: FastAPI, client: AsyncClient, mocks) -> None:
    # 1. a normal job resolves the song and fetches Songsterr #2
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "oasis wonderwall"}})
    first = await poll(client, r.json()["id"])
    assert first["status"] == "done", first
    song_id, first_tab = first["song_id"], first["tab_id"]

    # 2. browse: Songsterr (score desc) -> UG -> audio, tab_id filled for the fetched one
    r = await client.post(f"/api/v1/songs/{song_id}/candidates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["song_id"] == song_id and body["warnings"] == []
    cands = body["candidates"]
    sources = [c["source"] for c in cands]
    assert sources[:10] == ["songsterr"] * 10
    assert set(sources[10:-1]) == {"ultimate_guitar"} and 1 <= len(sources[10:-1]) <= 10
    assert sources[-1] == "audio"
    assert cands[0]["external_id"] == "2" and cands[0]["tab_id"] == first_tab
    assert cands[0]["score"] == 1.0 and cands[0]["track_count"] == 14 and cands[0]["kind"]
    assert cands[0]["available"] is True and cands[0]["reason"] is None
    assert all(c["tab_id"] is None for c in cands[1:])
    assert all(c["kind"] in {"Tabs", "Chords"} for c in cands if c["source"] == "ultimate_guitar")
    audio = cands[-1]
    assert audio["external_id"] == "audio" and audio["available"] is False
    assert "yt-dlp fetching is disabled" in audio["reason"]
    assert set(cands[0]) == {
        "source", "external_id", "title", "artist", "score", "kind", "rating", "votes",
        "track_count", "url", "tab_id", "available", "reason",
    }  # fmt: skip

    r = await client.post(f"/api/v1/songs/{song_id}/candidates", json={"limit": 2})
    limited = r.json()["candidates"]
    assert [c["source"] for c in limited] == ["songsterr", "songsterr", "ultimate_guitar",
                                              "ultimate_guitar", "audio"]  # fmt: skip

    # 3. "not this one, next": song_id-only job with #2 excluded picks #402823
    r = await client.post(
        "/api/v1/jobs",
        json={"song_id": song_id, "exclude": [{"source": "songsterr", "external_id": "2"}]},
    )
    assert r.status_code == 201, r.text
    second = await poll(client, r.json()["id"])
    assert second["status"] == "done", second
    assert second["song_id"] == song_id and second["tab_id"] != first_tab
    assert tier(second, "resolve")["message"] == tier(first, "resolve")["message"]
    ss = tier(second, "songsterr")
    assert ss["detail"]["excluded"] == 1 and ss["detail"]["picked"]["songId"] == 402823
    # the request (with exclude / song_id) is persisted in the job row
    async with app.state.session_factory() as s:
        stored = await JobRepo(s).get(second["id"])
    assert stored is not None and stored.request.song_id == song_id
    assert [(e.source, e.external_id) for e in stored.request.exclude] == [("songsterr", "2")]
    assert second["request"]["exclude"] == [{"source": "songsterr", "external_id": "2"}]

    # 4. fetch exactly one UG candidate; only that tier runs
    r = await client.post(
        "/api/v1/jobs",
        json={
            "song_id": song_id,
            "candidate": {"source": "ultimate_guitar", "external_id": "2223387"},
        },
    )
    third = await poll(client, r.json()["id"])
    assert third["status"] == "done", third
    assert [t["tier"] for t in third["tiers"]] == ["resolve", "ultimate_guitar"]
    assert tier(third, "ultimate_guitar")["detail"]["picked"]["targeted"] is True
    assert third["request"]["candidate"] == {"source": "ultimate_guitar", "external_id": "2223387"}
    tab = (await client.get(f"/api/v1/tabs/{third['tab_id']}")).json()
    assert tab["source_ref"] == "ug:2223387"

    # 5. browsing again links both fetched candidates to their tabs
    cands = (await client.post(f"/api/v1/songs/{song_id}/candidates")).json()["candidates"]
    by_key = {(c["source"], c["external_id"]): c for c in cands}
    assert by_key[("songsterr", "2")]["tab_id"] == first_tab
    assert by_key[("songsterr", "402823")]["tab_id"] == second["tab_id"]
    assert by_key[("ultimate_guitar", "2223387")]["tab_id"] == third["tab_id"]


async def test_candidates_unknown_song_is_404(client: AsyncClient) -> None:
    r = await client.post("/api/v1/songs/nope/candidates")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_candidates_reports_source_failures_as_warnings(client: AsyncClient, mocks) -> None:
    song = (await client.post("/api/v1/songs/resolve", json={"raw": "Oasis - Wonderwall"})).json()
    mocks.get(f"{UG_URL}/search.php").mock(return_value=httpx.Response(403, text="cf-challenge"))
    mocks.get(f"{BASE_URL}/api/songs").mock(return_value=httpx.Response(200, json=[]))
    body = (await client.post(f"/api/v1/songs/{song['id']}/candidates")).json()
    assert [c["source"] for c in body["candidates"]] == ["audio"]
    assert sorted(w.split(":")[0] for w in body["warnings"]) == ["songsterr", "ultimate_guitar"]
    assert any("blocked" in w for w in body["warnings"])
    assert any("no results" in w for w in body["warnings"])


async def test_song_id_only_job_creation(client: AsyncClient, mocks) -> None:
    song = (await client.post("/api/v1/songs/resolve", json={"raw": "Oasis - Wonderwall"})).json()
    r = await client.post("/api/v1/jobs", json={"song_id": song["id"]})
    assert r.status_code == 201 and r.json()["request"]["song_id"] == song["id"]
    job = await poll(client, r.json()["id"])
    assert job["status"] == "done" and job["song_id"] == song["id"]
    assert tier(job, "resolve")["detail"]["song_id"] == song["id"]

    r = await client.post("/api/v1/jobs", json={"song_id": "ghost"})
    assert r.status_code == 201
    job = await poll(client, r.json()["id"])
    assert job["status"] == "failed" and "not found" in job["error"]
    assert (await client.post("/api/v1/jobs", json={"exclude": []})).status_code == 422
    r = await client.post("/api/v1/jobs", json={"song_id": "x", "candidate": {"source": "nope"}})
    assert r.status_code == 422
