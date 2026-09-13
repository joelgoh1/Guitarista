"""Audio tier end-to-end: upload wav -> job(tiers=[audio]) -> tab. Uses the fake sidecar
(``GUITARISTA_ML_CMD`` from conftest) and the real ffmpeg on this machine."""

from __future__ import annotations

import asyncio
import io
import math
import os
import shutil
import struct
import time
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from guitarista_api.main import create_app
from guitarista_api.settings import Settings


def _sources(tiers):
    """Tier entries excluding the song-resolution step."""
    return [t for t in tiers if t["tier"] != "resolve"]


HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")

GUITAR_TONES = [(82.41, 40), (110.0, 45), (146.83, 50)]  # E2 A2 D3


def synth_wav(
    tones: list[tuple[float, int]] = GUITAR_TONES, seconds_per_tone: float = 1.0, sr: int = 22050
) -> bytes:
    """Sequential plucked-string-like tones (fundamental + 2nd/3rd harmonics, decaying)."""
    frames = bytearray()
    n = int(seconds_per_tone * sr)
    for freq, _ in tones:
        for i in range(n):
            t = i / sr
            env = math.exp(-2.0 * t) * (min(1.0, t / 0.01))
            v = (
                math.sin(2 * math.pi * freq * t)
                + 0.5 * math.sin(2 * math.pi * 2 * freq * t)
                + 0.25 * math.sin(2 * math.pi * 3 * freq * t)
            )
            frames += struct.pack("<h", int(max(-1.0, min(1.0, 0.5 * env * v)) * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_songsterr=False,
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


async def poll(client: AsyncClient, job_id: str, max_wait: float = 60) -> dict:
    async with asyncio.timeout(max_wait):
        while True:
            job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if job["status"] in {"done", "failed", "cancelled"}:
                return job
            await asyncio.sleep(0.02)


def tab_notes(tab: dict) -> list[tuple[int, int, int | None]]:
    return [
        (n["string"], n["fret"], n["pitch_midi"])
        for m in tab["tracks"][0]["measures"]
        for v in m["voices"]
        for b in v["beats"]
        for n in b["notes"]
    ]


async def test_upload_audio_validation(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/uploads/audio", files={"file": ("x.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 422 and "unsupported audio type" in r.json()["detail"]
    r = await client.post(
        "/api/v1/uploads/audio", files={"file": ("x.mp3", b"not really audio", "audio/mpeg")}
    )
    assert r.status_code == 422 and "does not look like an audio file" in r.json()["detail"]


@needs_ffmpeg
async def test_upload_audio_then_audio_job(app: FastAPI, client: AsyncClient) -> None:
    wav = synth_wav(seconds_per_tone=0.3)
    r = await client.post("/api/v1/uploads/audio", files={"file": ("riff.wav", wav, "audio/wav")})
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["filename"] == "riff.wav" and up["sample_rate"] == 22050
    assert up["duration_s"] is not None and abs(up["duration_s"] - 0.9) < 0.05
    stored = Path(app.state.settings.uploads_dir) / f"{up['upload_id']}.wav"
    assert stored.exists()

    r = await client.post(
        "/api/v1/jobs",
        json={"upload_id": up["upload_id"], "tiers": ["audio"], "song": {"raw": "Test Riff"}},
    )
    assert r.status_code == 201, r.text
    job = await poll(client, r.json()["id"])
    assert job["status"] == "done", job
    assert [t["tier"] for t in _sources(job["tiers"])] == ["audio"]
    tier = _sources(job["tiers"])[0]
    assert tier["status"] == "success" and tier["detail"]["stem"] == "mix"
    assert tier["detail"]["deterministic"] is False
    assert tier["detail"]["transcription"]["notes"] == 3
    assert tier["detail"]["input"]["kind"] == "upload"

    r = await client.get(f"/api/v1/tabs/{job['tab_id']}")
    tab = r.json()
    assert tab["source"] == "audio" and tab["confidence"] == 0.8  # mean note confidence
    assert tab["tempo_bpm"] == 60.0
    assert tab_notes(tab) == [(6, 0, 40), (5, 0, 45), (4, 0, 50)]
    assert any("mix stem" in w for w in tab["warnings"])
    assert any("aligned to tracked beats" in w for w in tab["warnings"])
    assert any("full mix" in w for w in tab["warnings"])
    assert tier["detail"]["solver"]["cost_profile"] == "tabgen"

    r = await client.get(f"/api/v1/tabs/{job['tab_id']}", params={"format": "alphatex"})
    assert r.status_code == 200
    assert r.text.startswith('\\title "Test Riff"') and "0.6" in r.text and "0.4" in r.text

    health = (await client.get("/api/v1/health")).json()
    assert health["features"]["ml_sidecar_ok"] is True
    assert health["features"]["separation_available"] is False
    assert health["ffmpeg"] is True and isinstance(health["ytdlp"], bool)
    assert health["tiers"][-1] == "audio"


@needs_ffmpeg
async def test_audio_job_upload_only_names_song_after_upload(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("a.wav", synth_wav(seconds_per_tone=0.2), "audio/wav")},
    )
    up = r.json()
    r = await client.post("/api/v1/jobs", json={"upload_id": up["upload_id"], "tiers": ["audio"]})
    job = await poll(client, r.json()["id"])
    assert job["status"] == "done" and job["song_id"]


async def test_audio_tier_skipped_without_upload(client: AsyncClient) -> None:
    r = await client.post("/api/v1/jobs", json={"song": {"raw": "x"}, "tiers": ["audio"]})
    job = await poll(client, r.json()["id"])
    assert job["status"] == "failed"
    assert _sources(job["tiers"])[0]["status"] == "skipped"
    assert "yt-dlp fetching is disabled" in _sources(job["tiers"])[0]["message"]


async def test_separation_requested_but_unavailable_warns(
    app: FastAPI, client: AsyncClient, monkeypatch
) -> None:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")
    app.state.settings.enable_separation = True
    r = await client.post(
        "/api/v1/uploads/audio",
        files={"file": ("a.wav", synth_wav(seconds_per_tone=0.2), "audio/wav")},
    )
    r = await client.post(
        "/api/v1/jobs", json={"upload_id": r.json()["upload_id"], "tiers": ["audio"]}
    )
    job = await poll(client, r.json()["id"])
    assert job["status"] == "done"
    tab = (await client.get(f"/api/v1/tabs/{job['tab_id']}")).json()
    assert any("Demucs is not installed" in w for w in tab["warnings"])


@pytest.mark.ml
@pytest.mark.skipif(
    os.environ.get("GUITARISTA_TEST_ML") != "1",
    reason="set GUITARISTA_TEST_ML=1 to run the real sidecar",
)
@needs_ffmpeg
async def test_real_sidecar_transcribes_three_tones(tmp_path: Path) -> None:
    """Runs ``uv run --directory ../ml guitarista-ml`` for real (basic-pitch); ~5-10 s."""
    settings = Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_songsterr=False,
        ml_cmd="uv run --directory ../ml guitarista-ml",
        tier_timeout_audio=300,
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/uploads/audio", files={"file": ("tones.wav", synth_wav(), "audio/wav")}
            )
            assert r.status_code == 201, r.text
            t0 = time.monotonic()
            r = await client.post(
                "/api/v1/jobs",
                json={
                    "upload_id": r.json()["upload_id"],
                    "tiers": ["audio"],
                    "song": {"raw": "Tones"},
                },
            )
            job = await poll(client, r.json()["id"], max_wait=300)
            elapsed = time.monotonic() - t0
            assert job["status"] == "done", job
            tab = (await client.get(f"/api/v1/tabs/{job['tab_id']}")).json()
            pitches = {p for _, _, p in tab_notes(tab)}
            assert {40, 45, 50} <= pitches, f"detected {sorted(pitches)}"
            assert 0.0 < tab["confidence"] <= 1.0
            n = len(tab_notes(tab))
            print(f"\nreal sidecar: {n} notes, pitches {sorted(pitches)}, {elapsed:.1f}s")


@needs_ffmpeg
async def test_tabcnn_model_hints_steer_frettings(tmp_path: Path, monkeypatch) -> None:
    """With ``audio_model=tabcnn`` the sidecar's string/fret hints reach the solver, which follows
    them even where the classic heuristics would pick open strings."""
    monkeypatch.setenv("FAKE_ML_TABCNN", "1")
    settings = Settings(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_songsterr=False,
        audio_model="tabcnn",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = (await client.get("/api/v1/health")).json()
            assert health["features"]["tabcnn_available"] is True
            assert health["features"]["audio_model"] == "tabcnn"
            r = await client.post(
                "/api/v1/uploads/audio",
                files={"file": ("a.wav", synth_wav(seconds_per_tone=0.2), "audio/wav")},
            )
            r = await client.post(
                "/api/v1/jobs", json={"upload_id": r.json()["upload_id"], "tiers": ["audio"]}
            )
            job = await poll(client, r.json()["id"])
            assert job["status"] == "done", job
            tier = _sources(job["tiers"])[0]
            assert tier["detail"]["transcription"]["model"] == "fake/tabcnn"
            assert tier["detail"]["transcription"]["string_hints"] == 3
            assert tier["detail"]["solver"]["hinted_events"] == 3
            assert tier["detail"]["solver"]["hint_misses"] == 0
            tab = (await client.get(f"/api/v1/tabs/{job['tab_id']}")).json()
            assert tab_notes(tab) == [(6, 0, 40), (6, 5, 45), (5, 5, 50)]
