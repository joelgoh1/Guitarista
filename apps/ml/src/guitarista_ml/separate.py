"""Source separation with Demucs (optional extra ``separate``).

torch/demucs are imported lazily so the base install never pays for them.
Model weights are cached under ``$TORCH_HOME`` (set by the caller).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from guitarista_ml.io import CliError, emit_progress, quiet_stdout
from guitarista_ml.schema import SeparateOptions, SeparateResult

_INSTALL_HINT = "run `uv sync --extra separate` in apps/ml to install demucs/torch/torchaudio"


def _require_demucs() -> None:
    missing = [m for m in ("torch", "torchaudio", "demucs") if importlib.util.find_spec(m) is None]
    if missing:
        raise CliError(
            f"source separation unavailable: {', '.join(missing)} not installed; {_INSTALL_HINT}",
            type="missing_dependency",
            exit_code=3,
        )


def _pick_device(requested: str) -> str:
    import torch

    if requested == "cpu":
        return "cpu"
    mps_ok = torch.backends.mps.is_available()
    if requested == "mps":
        if not mps_ok:
            raise CliError("MPS device requested but not available", type="invalid_input", exit_code=2)
        return "mps"
    return "mps" if mps_ok else "cpu"


def separate(in_path: Path, out_dir: Path, opts: SeparateOptions) -> SeparateResult:
    if not in_path.is_file():
        raise CliError(f"input file not found: {in_path}", type="invalid_input", exit_code=2)
    if in_path.suffix.lower() != ".wav":
        raise CliError("only .wav input is accepted; convert with ffmpeg first", type="invalid_input", exit_code=2)
    _require_demucs()

    emit_progress(0.02, "load")
    with quiet_stdout():
        import torch
        from demucs.api import Separator, save_audio

    device = _pick_device(opts.device)
    emit_progress(0.05, f"model:{opts.model}:{device}")

    def _cb(info: dict) -> None:
        # demucs reports per-segment progress; map it onto 0.1..0.9
        total = info.get("audio_length") or 0
        offset = info.get("segment_offset") or 0
        if total:
            emit_progress(0.1 + 0.8 * min(1.0, offset / total), "separate")

    try:
        with quiet_stdout():
            separator = Separator(model=opts.model, device=device, progress=False, callback=_cb)
            _, stems = separator.separate_audio_file(in_path)
    except Exception as exc:
        if device == "mps":
            # MPS has known op gaps; fall back to CPU rather than fail the tier.
            emit_progress(0.1, "separate:cpu-fallback")
            with quiet_stdout():
                separator = Separator(model=opts.model, device="cpu", progress=False, callback=_cb)
                _, stems = separator.separate_audio_file(in_path)
        else:
            raise CliError(f"demucs separation failed: {exc!r}", type="inference", exit_code=4) from exc

    available = set(stems)
    wanted = [s for s in opts.stems if s in available]
    unknown = [s for s in opts.stems if s not in available]
    if not wanted:
        raise CliError(
            f"none of the requested stems {opts.stems} exist in model {opts.model} (has {sorted(available)})",
            type="invalid_input",
            exit_code=2,
        )
    if unknown:
        emit_progress(0.9, f"skip-unknown-stems:{','.join(unknown)}")

    emit_progress(0.92, "write")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name in wanted:
        target = out_dir / f"{in_path.stem}.{name}.wav"
        with quiet_stdout():
            save_audio(stems[name].to("cpu"), str(target), samplerate=separator.samplerate)
        paths[name] = str(target)
    del stems
    if device == "mps":
        torch.mps.empty_cache()
    emit_progress(1.0, "done")
    return {"stems": paths, "model": opts.model}
