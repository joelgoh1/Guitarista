from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from guitarista_api.adapters.ml_sidecar import (
    MLSidecar,
    SidecarError,
    TranscribeParams,
    parse_transcription,
)

FAKE = Path(__file__).parents[2] / "fixtures" / "fake_ml" / "guitarista_ml_fake.py"


@pytest.fixture
def sidecar(tmp_path: Path) -> MLSidecar:
    return MLSidecar(f"{sys.executable} {FAKE}", models_dir=tmp_path / "models")


def test_cmd_is_shlex_split_and_torch_home_set(tmp_path: Path) -> None:
    s = MLSidecar('uv run --directory "../my ml" guitarista-ml', models_dir=tmp_path)
    assert s.cmd == ["uv", "run", "--directory", "../my ml", "guitarista-ml"]
    assert s.env["TORCH_HOME"] == str(tmp_path.resolve() / "torch")
    with pytest.raises(ValueError):
        MLSidecar("")


async def test_probe_is_cached(sidecar: MLSidecar) -> None:
    assert not sidecar.probed and sidecar.capabilities is None
    caps = await sidecar.probe()
    assert caps is not None and caps.basic_pitch and not caps.demucs and caps.device == "cpu"
    assert sidecar.probed and sidecar.capabilities == caps
    sidecar.cmd = ["/definitely/not/a/binary"]
    assert await sidecar.probe() is caps  # cached, command not re-run
    assert await sidecar.probe(force=True) is None
    assert sidecar.probe_error and "not found" in sidecar.probe_error


async def test_probe_missing_command_returns_none(tmp_path: Path) -> None:
    s = MLSidecar("/no/such/guitarista-ml", models_dir=tmp_path)
    assert await s.probe() is None
    assert s.probed and s.capabilities is None
    assert s.probe_error and "uv sync" in s.probe_error


async def test_version(sidecar: MLSidecar) -> None:
    assert await sidecar.version() == "0.0.0-fake"


async def test_transcribe_parses_result_and_forwards_progress(
    sidecar: MLSidecar, tmp_path: Path
) -> None:
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"RIFF....WAVE")
    seen: list[tuple[float, str]] = []

    async def on_progress(value: float, stage: str) -> None:
        seen.append((value, stage))

    result = await sidecar.transcribe(
        wav, tmp_path / "out" / "t.json", TranscribeParams(), on_progress=on_progress
    )
    assert [n.pitch_midi for n in result.notes] == [40, 45, 50]
    assert [n.onset_s for n in result.notes] == [0.0, 1.0, 2.0]
    assert result.tempo_bpm == 60.0 and result.duration_s == 3.0
    assert all(n.confidence == n.velocity for n in result.notes)
    assert seen == [(0.0, "load"), (0.5, "infer"), (1.0, "done")]  # chatter line ignored


async def test_transcribe_sync_progress_callback_and_args(
    sidecar: MLSidecar, tmp_path: Path
) -> None:
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"x")
    seen: list[float] = []
    params = TranscribeParams(fmin=80, fmax=1300, estimate_tempo=False, onset=0.4)
    assert params.to_args() == [
        "--model",
        "basic-pitch",
        "--onset",
        "0.4",
        "--fmin",
        "80",
        "--fmax",
        "1300",
    ]
    result = await sidecar.transcribe(
        wav, tmp_path / "t.json", params, on_progress=lambda v, _stage: seen.append(v)
    )
    assert result.tempo_bpm is None and seen == [0.0, 0.5, 1.0]


async def test_transcribe_invalid_input_raises(sidecar: MLSidecar, tmp_path: Path) -> None:
    with pytest.raises(SidecarError) as info:
        await sidecar.transcribe(tmp_path / "missing.wav", tmp_path / "t.json")
    assert info.value.exit_code == 2 and info.value.type == "invalid_input"
    assert "missing.wav" in info.value.message


async def test_transcribe_inference_failure(
    sidecar: MLSidecar, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FAKE_ML_FAIL", "1")
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"x")
    with pytest.raises(SidecarError) as info:
        await sidecar.transcribe(wav, tmp_path / "t.json")
    assert (info.value.exit_code, info.value.type) == (4, "inference")
    assert "exploded" in str(info.value)


async def test_separate_exit_3_is_demucs_missing(sidecar: MLSidecar, tmp_path: Path) -> None:
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"x")
    with pytest.raises(SidecarError) as info:
        await sidecar.separate(wav, tmp_path / "stems")
    assert info.value.exit_code == 3 and info.value.demucs_missing
    assert info.value.type == "missing_dependency"


async def test_cancellation_terminates_process(
    sidecar: MLSidecar, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FAKE_ML_SLEEP", "30")
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"x")
    started: list[float] = []
    task = asyncio.create_task(
        sidecar.transcribe(wav, tmp_path / "t.json", on_progress=lambda v, s: started.append(v))
    )
    for _ in range(200):  # wait for the first progress line => process is up
        if started:
            break
        await asyncio.sleep(0.02)
    assert started, "fake sidecar never started"
    t0 = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - t0 < 5.0


async def test_unknown_command_without_json(tmp_path: Path) -> None:
    # A command that exits non-zero and prints no JSON => "crash" error with stderr tail.
    s = MLSidecar([sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(9)"])
    with pytest.raises(SidecarError) as info:
        await s.version()
    assert info.value.exit_code == 9 and info.value.type == "crash" and "boom" in info.value.message


async def test_success_without_json_is_output_error() -> None:
    s = MLSidecar([sys.executable, "-c", "print('not json')"])
    with pytest.raises(SidecarError) as info:
        await s.version()
    assert info.value.type == "output"


def test_parse_transcription_normalizes() -> None:
    raw = {
        "notes": [
            {
                "onset_s": -0.01,
                "offset_s": 0.5,
                "pitch_midi": 40,
                "velocity": 1.7,
                "confidence": None,
            },
            {"onset_s": 1, "offset_s": 1.5, "pitch_midi": 45, "velocity": 0.3, "confidence": 0.9},
        ],
        "tempo_bpm": None,
        "duration_s": 2.0,
        "stem": "guitar",
        "model": "m",
        "source_audio": "/x.wav",
    }
    result = parse_transcription(raw)
    assert result.notes[0].onset_s == 0.0 and result.notes[0].velocity == 1.0
    assert result.notes[0].confidence == 1.0 and result.notes[1].confidence == 0.9
    assert result.model == "m" and result.tempo_bpm is None


def test_env_passthrough(tmp_path: Path) -> None:
    s = MLSidecar("x", env={"FOO": "1"}, models_dir=tmp_path)
    assert s.env["FOO"] == "1" and "TORCH_HOME" in s.env
