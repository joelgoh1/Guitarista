"""Report which ML capabilities are available without ever crashing.

Only imports torch when it is actually installed (it is a heavy optional extra).
"""

from __future__ import annotations

import importlib.util
import logging

from guitarista_ml.io import quiet_stdout
from guitarista_ml.schema import Backend, ProbeResult

_SUFFIX_TO_BACKEND: dict[str, Backend] = {
    "tf": "tf",
    "coreml": "coreml",
    "tflite": "tflite",
    "onnx": "onnx",
}


def _installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def probe_basic_pitch() -> tuple[bool, Backend | None]:
    if not _installed("basic_pitch"):
        return False, None
    try:
        logging.disable(logging.WARNING)
        with quiet_stdout():
            import basic_pitch
            import basic_pitch.inference  # noqa: F401  (pulls resampy/librosa; fails if broken)
        suffix = getattr(basic_pitch, "_default_model_type", None)
        backend = _SUFFIX_TO_BACKEND.get(getattr(suffix, "name", ""), None)
        return True, backend
    except Exception:
        return False, None
    finally:
        logging.disable(logging.NOTSET)


def probe_torch() -> tuple[str | None, str]:
    """Return (torch version or None, preferred device)."""
    if not _installed("torch"):
        return None, "cpu"
    try:
        with quiet_stdout():
            import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        return str(torch.__version__), device
    except Exception:
        return None, "cpu"


def probe_tabcnn() -> bool:
    """onnxruntime importable and the shipped weights present (no torch needed)."""
    if not _installed("onnxruntime"):
        return False
    try:
        from guitarista_ml.tabcnn.infer import weights_available

        return weights_available()
    except Exception:
        return False


def probe() -> ProbeResult:
    bp_ok, backend = probe_basic_pitch()
    torch_version, device = probe_torch()
    demucs_ok = _installed("demucs") and torch_version is not None
    return {
        "basic_pitch": bp_ok,
        "backend": backend,
        "demucs": demucs_ok,
        "tabcnn": probe_tabcnn(),
        "device": device,  # type: ignore[typeddict-item]
        "torch": torch_version,
    }
