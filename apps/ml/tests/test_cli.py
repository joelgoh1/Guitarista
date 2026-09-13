"""End-to-end tests for the guitarista-ml CLI (run via subprocess, as apps/api does)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 22050
# E2, A2, D3 — the three lowest open strings of a standard-tuned guitar.
TONES = [(82.41, 40), (110.0, 45), (146.83, 50)]


def run_cli(*args: str, check: bool = True) -> tuple[dict, str, int]:
    """Run the CLI in the current interpreter's environment; return (last-line JSON, stderr, exit code)."""
    proc = subprocess.run(
        [sys.executable, "-m", "guitarista_ml", *args],
        capture_output=True,
        text=True,
        timeout=600,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"no stdout from CLI; stderr:\n{proc.stderr}"
    payload = json.loads(lines[-1])
    if check:
        assert proc.returncode == 0, f"exit {proc.returncode}: {payload}\n{proc.stderr}"
    return payload, proc.stderr, proc.returncode


def synth_wav(path: Path, seconds_per_tone: float = 1.0) -> None:
    """Three sequential plucked-string-like tones with 2nd/3rd harmonics."""
    chunks = []
    for freq, _ in TONES:
        t = np.arange(int(SR * seconds_per_tone)) / SR
        env = np.minimum(1.0, t * 50) * np.exp(-t * 1.5)  # fast attack, slow decay
        wave = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 2 * freq * t) + 0.25 * np.sin(2 * np.pi * 3 * freq * t)
        chunks.append(env * wave)
    y = np.concatenate(chunks).astype(np.float32)
    y *= 0.5 / np.abs(y).max()
    sf.write(str(path), y, SR)


def test_version() -> None:
    payload, _, _ = run_cli("version")
    assert payload == {"version": "0.1.0"}


def test_probe_shape() -> None:
    payload, _, _ = run_cli("probe")
    assert set(payload) == {"basic_pitch", "backend", "demucs", "tabcnn", "device", "torch"}
    assert isinstance(payload["tabcnn"], bool)
    assert isinstance(payload["basic_pitch"], bool)
    assert payload["backend"] in {"coreml", "tf", "onnx", "tflite", None}
    assert isinstance(payload["demucs"], bool)
    assert payload["device"] in {"mps", "cpu"}
    assert payload["torch"] is None or isinstance(payload["torch"], str)
    # This project installs basic-pitch as a hard dependency, so it must be usable.
    assert payload["basic_pitch"] is True
    assert payload["backend"] is not None


def test_transcribe_missing_file_is_json_error(tmp_path: Path) -> None:
    payload, _, code = run_cli("transcribe", str(tmp_path / "nope.wav"), str(tmp_path / "out.json"), check=False)
    assert code == 2
    assert payload["type"] == "invalid_input"
    assert "not found" in payload["error"]


def test_transcribe_rejects_non_wav(tmp_path: Path) -> None:
    bad = tmp_path / "song.mp3"
    bad.write_bytes(b"\x00" * 16)
    payload, _, code = run_cli("transcribe", str(bad), str(tmp_path / "out.json"), check=False)
    assert code == 2
    assert payload["type"] == "invalid_input"


def test_transcribe_three_tones(tmp_path: Path) -> None:
    wav = tmp_path / "three.wav"
    out = tmp_path / "three.json"
    synth_wav(wav)

    t0 = time.perf_counter()
    payload, stderr, _ = run_cli("transcribe", str(wav), str(out), "--estimate-tempo")
    elapsed = time.perf_counter() - t0

    assert payload["ok"] is True
    assert payload["out"] == str(out)
    assert payload["note_count"] >= 3

    # progress lines on stderr are JSON and monotonic
    progress = [json.loads(ln) for ln in stderr.splitlines() if ln.startswith('{"progress"')]
    assert progress and progress[-1]["progress"] == 1.0
    assert all(a["progress"] <= b["progress"] for a, b in zip(progress, progress[1:]))

    result = json.loads(out.read_text())
    assert result["stem"] == "mix"
    assert result["model"] == "basic-pitch/icassp2022"
    assert result["source_audio"] == str(wav)
    assert result["duration_s"] == pytest.approx(3.0, abs=0.01)
    assert result["tempo_bpm"] is None or result["tempo_bpm"] > 0
    assert isinstance(result["beats_s"], list)
    assert all(b >= 0 for b in result["beats_s"]) and result["beats_s"] == sorted(result["beats_s"])

    notes = result["notes"]
    for n in notes:
        assert n["onset_s"] < n["offset_s"]
        assert 0.0 <= n["velocity"] <= 1.0
        assert n["pitch_bend"] is None or all(isinstance(b, int) for b in n["pitch_bend"])
        assert n["confidence"] == n["velocity"]

    pitches = {n["pitch_midi"] for n in notes}
    expected = {midi for _, midi in TONES}
    assert expected <= pitches, f"missing {expected - pitches}; detected {sorted(pitches)}"

    # each expected pitch starts within its own 1 s window
    for i, (_, midi) in enumerate(TONES):
        onsets = [n["onset_s"] for n in notes if n["pitch_midi"] == midi]
        assert any(i - 0.15 <= o <= i + 0.3 for o in onsets), f"pitch {midi} onsets {onsets}"

    print(f"\ndetected pitches: {sorted(pitches)}; transcribe wall time: {elapsed:.2f}s")


def test_separate_without_extra_is_clear_error(tmp_path: Path) -> None:
    try:
        import demucs  # noqa: F401

        pytest.skip("demucs installed; error path not applicable")
    except ImportError:
        pass
    wav = tmp_path / "x.wav"
    sf.write(str(wav), np.zeros(SR, dtype=np.float32), SR)
    payload, _, code = run_cli("separate", str(wav), str(tmp_path / "stems"), check=False)
    assert code == 3
    assert payload["type"] == "missing_dependency"
    assert "uv sync --extra separate" in payload["error"]
