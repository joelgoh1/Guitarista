from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from guitarista_api.adapters.songsterr.client import BASE_URL, CDN_URL
from guitarista_api.domain.tab import Tab, Track
from guitarista_api.main import create_app
from guitarista_api.settings import Settings
from guitarista_api.sources.base import SourceResult


def _sources(tiers):
    """Tier entries excluding the song-resolution step."""
    return [t for t in tiers if t["tier"] != "resolve"]


META_URL = f"{BASE_URL}/api/meta/2"
TRACK_URL = CDN_URL + "/2/8047059/v0-3-2-hmpMBN-NNIVq9p59/{idx}.json"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        tier_timeout_songsterr=0.3,
        enable_ug=False,  # UG has its own integration test; keep these off the network
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
def songsterr_mock(songsterr_fixtures) -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.get(f"{BASE_URL}/api/songs").mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["search"])
        )
        router.get(META_URL).mock(return_value=httpx.Response(200, json=songsterr_fixtures["meta"]))
        router.get(TRACK_URL.format(idx=3)).mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["track_3"])
        )
        router.get(TRACK_URL.format(idx=6)).mock(
            return_value=httpx.Response(200, json=songsterr_fixtures["track_6"])
        )
        router.get(url__regex=rf"{CDN_URL}/.*").mock(return_value=httpx.Response(404))
        yield router


async def poll(client: AsyncClient, job_id: str, max_wait: float = 10) -> dict:
    async with asyncio.timeout(max_wait):
        while True:
            job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if job["status"] in {"done", "failed", "cancelled"}:
                return job
            await asyncio.sleep(0.02)


async def test_create_job_songsterr_success(client: AsyncClient, songsterr_mock) -> None:
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "oasis wonderwall"}})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] in {"queued", "running"} and job["request"]["song"]["raw"]

    job = await poll(client, job["id"])
    assert job["status"] == "done", job
    assert job["progress"] == 1.0 and job["song_id"] and job["tab_id"]
    tiers = job["tiers"]
    assert [t["tier"] for t in _sources(tiers)] == ["songsterr"]
    assert _sources(tiers)[0]["status"] == "success"
    assert _sources(tiers)[0]["detail"]["picked"]["songId"] == 2
    assert _sources(tiers)[0]["detail"]["llm_used"] is False
    assert _sources(tiers)[0]["detail"]["tracks"] == 2  # only 3 and 6 could be downloaded
    assert _sources(tiers)[0]["detail"]["skipped_tracks"]

    r = await client.get(f"/api/v1/tabs/{job['tab_id']}", params={"format": "alphatex"})
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert lines[0] == '\\title "Wonderwall"' and "\\capo 2" in lines
    r = await client.get(f"/api/v1/tabs/{job['tab_id']}")
    tab = r.json()
    assert tab["source"] == "songsterr" and tab["song_id"] == job["song_id"]
    assert len(tab["tracks"]) == 2 and tab["tracks"][0]["capo"] == 2

    r = await client.get("/api/v1/tabs", params={"song_id": job["song_id"]})
    assert [t["id"] for t in r.json()] == [job["tab_id"]]
    assert (await client.get("/api/v1/tabs", params={"song_id": "nope"})).json() == []

    r = await client.get("/api/v1/jobs", params={"status": "done"})
    assert [j["id"] for j in r.json()] == [job["id"]]
    assert (await client.get("/api/v1/jobs", params={"status": "failed"})).json() == []

    health = (await client.get("/api/v1/health")).json()
    assert health["tiers"][0] == "songsterr" and health["tiers"][-1] == "audio"
    assert health["features"]["jobs"] is True


async def test_legacy_query_key_and_validation(client: AsyncClient) -> None:
    r = await client.post("/api/v1/jobs", json={})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    r = await client.post("/api/v1/jobs", json={"song": {}})
    assert r.status_code == 422
    r = await client.post("/api/v1/jobs", json={"query": {"raw": "x"}})
    assert r.status_code == 201 and r.json()["request"]["song"]["raw"] == "x"

    # audio_url alone is enough to start a job, but it must be an http(s) URL.
    r = await client.post("/api/v1/jobs", json={"audio_url": "https://www.youtube.com/watch?v=abc"})
    assert r.status_code == 201
    assert r.json()["request"]["audio_url"] == "https://www.youtube.com/watch?v=abc"
    for bad in ("file:///etc/passwd", "not a url", "ftp://host/x"):
        r = await client.post("/api/v1/jobs", json={"audio_url": bad})
        assert r.status_code == 422, bad

    assert (await client.get("/api/v1/jobs/nope")).status_code == 404
    assert (await client.post("/api/v1/jobs/nope/cancel")).status_code == 404
    assert (await client.get("/api/v1/jobs/nope/events")).status_code == 404


async def test_job_fails_when_songsterr_has_no_match(client: AsyncClient, songsterr_mock) -> None:
    songsterr_mock.get(f"{BASE_URL}/api/songs").mock(return_value=httpx.Response(200, json=[]))
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "definitely not a song"}})
    job = await poll(client, r.json()["id"])
    assert job["status"] == "failed"
    assert _sources(job["tiers"])[0]["status"] == "failed"
    assert "no results" in _sources(job["tiers"])[0]["message"]
    assert job["error"].startswith("no tab found")


async def test_sse_stream_replays_and_ends(client: AsyncClient, songsterr_mock) -> None:
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "Oasis - Wonderwall"}})
    job_id = r.json()["id"]
    events: list[tuple[str, dict]] = []
    async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        name, data = None, ""
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data += line.split(":", 1)[1].strip()
            elif line == "" and name:
                events.append((name, json.loads(data) if data else {}))
                name, data = None, ""
    names = [n for n, _ in events]
    assert names[-1] == "end" and "done" in names
    assert "tier" in names and "progress" in names
    done = next(d for n, d in events if n == "done")
    assert done["tab_id"] and done["job"]["status"] == "done"
    tier_events = [d for n, d in events if n == "tier"]
    assert tier_events[-1]["tier"]["status"] == "success"
    assert all("job" in d for _, d in events if _ != "end")

    # a finished job replays its log and terminal event immediately
    events2: list[str] = []
    async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                events2.append(line.split(":", 1)[1].strip())
    assert events2 == ["tier", "tier", "done", "end"]


class SlowSource:
    name = "songsterr"
    deterministic = True

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def can_handle(self, request, song, ctx):
        return True, None

    async def fetch(self, request, song, ctx) -> SourceResult:
        await asyncio.sleep(self.delay)
        return SourceResult(tab=Tab(title=song.title, tracks=[Track()]))


async def test_cancel_running_job(app: FastAPI, client: AsyncClient) -> None:
    app.state.sources = [SlowSource(delay=30)]
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "slow song"}})
    job_id = r.json()["id"]
    await asyncio.sleep(0.05)
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    job = await poll(client, job_id)
    assert job["status"] == "cancelled" and _sources(job["tiers"])[0]["status"] == "cancelled"
    assert app.state.job_manager.running_ids() == []
    # cancelling again is a no-op returning the persisted job
    assert (await client.post(f"/api/v1/jobs/{job_id}/cancel")).json()["status"] == "cancelled"


async def test_tier_timeout_from_settings(app: FastAPI, client: AsyncClient) -> None:
    app.state.sources = [SlowSource(delay=5)]  # settings.tier_timeout_songsterr = 0.3
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "slow song"}})
    job = await poll(client, r.json()["id"])
    assert job["status"] == "failed"
    assert _sources(job["tiers"])[0]["status"] == "timeout"


async def test_interrupted_jobs_marked_on_boot(settings: Settings) -> None:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.sources = [SlowSource(delay=30)]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            job_id = (await c.post("/api/v1/jobs", json={"song": {"raw": "x"}})).json()["id"]
            await asyncio.sleep(0.05)
        # simulate a hard stop: bypass the manager's cancel path
        from guitarista_api.db.repo import JobRepo

        task = app.state.job_manager._tasks[job_id]
        app.state.job_manager._tasks.clear()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with app.state.session_factory() as s:
            job = await JobRepo(s).get(job_id)
            assert job is not None
            job.status = "running"
            await JobRepo(s).upsert(job)
    app2 = create_app(settings)
    async with app2.router.lifespan_context(app2):
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            job = (await c.get(f"/api/v1/jobs/{job_id}")).json()
            assert job["status"] == "interrupted"
            r = await c.get("/api/v1/jobs", params={"status": "interrupted"})
            assert [j["id"] for j in r.json()] == [job_id]


async def test_songs_resolve_and_search_without_spotify(client: AsyncClient) -> None:
    r = await client.post("/api/v1/songs/resolve", json={"raw": "Oasis - Wonderwall"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Wonderwall" and body["artist"] == "Oasis"
    assert body["normalized_query"] == "oasis wonderwall"
    r = await client.post("/api/v1/songs/resolve", json={})
    assert r.status_code == 422
    r = await client.get("/api/v1/songs/search", params={"q": "wonder"})
    assert r.status_code == 200 and r.json() == []
    assert r.headers["x-spotify"] == "disabled"
