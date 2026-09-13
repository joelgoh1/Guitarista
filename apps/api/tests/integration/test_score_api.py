from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from guitarista_api.adapters.musescore import musescore_available, resolve_mscore
from guitarista_api.main import create_app
from guitarista_api.settings import Settings


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # tests run against the fake sidecar (GUITARISTA_ML_CMD, see conftest)
    assert body["features"]["ml_sidecar_ok"] is True
    assert body["features"]["separation_available"] is False
    assert set(body["features"]) >= {
        "spotify",
        "llm",
        "songsterr",
        "ug",
        "audio",
        "ytdlp",
        "separation",
    }


async def test_upload_score_to_tab_to_alphatex(client: AsyncClient, twinkle_bytes: bytes) -> None:
    files = {"file": ("twinkle.musicxml", twinkle_bytes, "application/xml")}
    r = await client.post("/api/v1/uploads/score", files=files)
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["parts"][0]["note_count"] == 42

    r = await client.post("/api/v1/score/tab", json={"upload_id": up["upload_id"]})
    assert r.status_code == 201, r.text
    tab = r.json()
    assert tab["source"] == "score" and len(tab["tracks"][0]["measures"]) == 12
    assert tab["title"] == "twinkle"

    r = await client.get(f"/api/v1/tabs/{tab['id']}", params={"format": "alphatex"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/x-alphatex")
    assert r.text.splitlines()[5] == "1.2.4 1.2 3.1 3.1 |"

    r = await client.get(f"/api/v1/tabs/{tab['id']}", params={"format": "ascii"})
    assert r.status_code == 200 and "E |" in r.text
    r = await client.get(f"/api/v1/tabs/{tab['id']}", params={"format": "musicxml"})
    assert r.status_code == 200 and "<score-partwise" in r.text

    r = await client.get("/api/v1/tabs")
    assert r.status_code == 200 and r.json()[0]["id"] == tab["id"]


async def test_score_tab_out_of_range_is_422_problem_json(
    client: AsyncClient, twinkle_bytes: bytes
) -> None:
    files = {"file": ("twinkle.musicxml", twinkle_bytes, "application/xml")}
    up = (await client.post("/api/v1/uploads/score", files=files)).json()
    # ukulele-like tuning cannot reach the low notes -> raise policy -> 422
    r = await client.post(
        "/api/v1/score/tab", json={"upload_id": up["upload_id"], "tuning": [81, 76, 72, 79]}
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "octave_shift" in r.json()["detail"]
    r = await client.post(
        "/api/v1/score/tab",
        json={
            "upload_id": up["upload_id"],
            "tuning": [81, 76, 72, 79],
            "out_of_range": "octave_shift",
        },
    )
    assert r.status_code == 201 and r.json()["warnings"]


async def test_unknown_upload_and_tab_are_404(client: AsyncClient) -> None:
    r = await client.post("/api/v1/score/tab", json={"upload_id": "nope"})
    assert r.status_code == 404
    r = await client.get("/api/v1/tabs/nope")
    assert r.status_code == 404


async def test_bad_upload_type_is_422(client: AsyncClient) -> None:
    r = await client.post("/api/v1/uploads/score", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 422


# ------------------------------------------------------------------ MuseScore-backed formats


async def test_health_reports_musescore(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.json()["features"]["musescore"] == musescore_available("mscore")


async def test_mscz_upload_without_musescore_explains_how_to_fix_it(
    tmp_path: Path, twinkle_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    monkeypatch.setenv("PATH", "")
    resolve_mscore.cache_clear()
    settings = Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        mscore_bin="definitely-not-installed",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # a real zip, so it clears the magic-byte guard and fails on the missing binary
            files = {"file": ("twinkle.mscz", b"PK\x03\x04rest", "application/octet-stream")}
            r = await c.post("/api/v1/uploads/score", files=files)
    resolve_mscore.cache_clear()
    assert r.status_code == 422
    assert "MuseScore" in r.json()["detail"] and "musescore.org" in r.json()["detail"]


async def test_mscz_that_is_not_a_zip_is_rejected_before_spawning(
    client: AsyncClient, twinkle_bytes: bytes
) -> None:
    files = {"file": ("fake.mscz", twinkle_bytes, "application/octet-stream")}
    r = await client.post("/api/v1/uploads/score", files=files)
    assert r.status_code == 422
    assert "does not look like a .mscz file" in r.json()["detail"]


async def test_unknown_suffix_lists_the_new_formats(client: AsyncClient) -> None:
    files = {"file": ("score.pdf", b"%PDF-1.4", "application/pdf")}
    r = await client.post("/api/v1/uploads/score", files=files)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert ".mscz" in detail and ".gp5" in detail and ".musicxml" in detail


async def test_midi_upload_still_works(client: AsyncClient, twinkle_midi_bytes: bytes) -> None:
    """The .mid branch of score_import._load had no coverage before."""
    files = {"file": ("twinkle.mid", twinkle_midi_bytes, "audio/midi")}
    r = await client.post("/api/v1/uploads/score", files=files)
    assert r.status_code == 201, r.text
    assert r.json()["parts"][0]["note_count"] > 0


@pytest.mark.musescore
@pytest.mark.skipif(not musescore_available("mscore"), reason="MuseScore is not installed")
async def test_mscz_converts_and_solves_end_to_end(
    client: AsyncClient, twinkle_mscz_bytes: bytes
) -> None:
    files = {"file": ("twinkle.mscz", twinkle_mscz_bytes, "application/octet-stream")}
    r = await client.post("/api/v1/uploads/score", files=files)
    assert r.status_code == 201, r.text
    up = r.json()
    # same music as twinkle.musicxml, so the same note count
    assert up["parts"][0]["note_count"] == 42

    r = await client.post("/api/v1/score/tab", json={"upload_id": up["upload_id"]})
    assert r.status_code == 201, r.text
    tab = r.json()
    assert tab["source"] == "score" and len(tab["tracks"][0]["measures"]) == 12
