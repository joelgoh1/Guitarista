"""TabCNN inference with onnxruntime (base install; never imports torch).

``TabCNNPredictor`` turns audio into per-frame class probabilities; ``decode`` smooths them
per string with a Viterbi pass, splits sustained runs at spectral-flux onsets and emits
``NoteEvent``s with canonical string numbers (1 = high E).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from guitarista_ml.schema import NoteEvent
from guitarista_ml.tabcnn.features import (
    FPS,
    HOP,
    MODEL_STRING_OPEN_MIDI,
    N_CLASSES,
    N_STRINGS,
    SR,
    context_windows,
    cqt_frames,
)
from guitarista_ml.tabcnn.labels import model_string_to_canonical

SHIPPED_WEIGHTS = Path(__file__).resolve().parents[1] / "models" / "tabcnn.onnx"
DEFAULT_WEIGHTS = Path(os.environ.get("GUITARISTA_TABCNN_WEIGHTS") or SHIPPED_WEIGHTS)
"""Override with ``GUITARISTA_TABCNN_WEIGHTS`` to A/B a candidate model without replacing the shipped one."""
TABCNN_MODEL = "tabcnn/guitarset"


def weights_available(path: Path = DEFAULT_WEIGHTS) -> bool:
    return path.is_file()


@dataclass(frozen=True, slots=True)
class DecodeOptions:
    switch_penalty: float = 2.0
    """Viterbi cost (in nats) for a string changing class between frames; 0 = plain argmax."""
    min_note_ms: float = 58.0
    split_on_onsets: bool = True
    min_prob: float = 0.3
    """Runs whose mean class probability falls below this are dropped."""


class TabCNNPredictor:
    def __init__(self, weights: Path = DEFAULT_WEIGHTS) -> None:
        import onnxruntime as ort

        if not weights.is_file():
            raise FileNotFoundError(f"TabCNN weights not found at {weights}")
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(weights), opts, providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.context = int(inp.shape[-1])

    def predict_frames(self, frames: np.ndarray, batch: int = 512) -> np.ndarray:
        """``(T, N_BINS)`` frames → ``(T, 6, 21)`` softmax probabilities."""
        if frames.shape[0] == 0:
            return np.zeros((0, N_STRINGS, N_CLASSES), dtype=np.float32)
        windows = context_windows(frames, self.context)[:, None, :, :].astype(np.float32)
        out = []
        for i in range(0, windows.shape[0], batch):
            (logits,) = self.session.run(None, {self.input_name: windows[i : i + batch]})
            out.append(_softmax(logits))
        return np.concatenate(out, axis=0)

    def predict_audio(self, y: np.ndarray) -> np.ndarray:
        return self.predict_frames(cqt_frames(y))


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return (e / e.sum(axis=-1, keepdims=True)).astype(np.float32)


def viterbi_classes(probs: np.ndarray, switch_penalty: float) -> np.ndarray:
    """``(T, 6, 21)`` → ``(T, 6)`` class path per string minimising -log p + switches."""
    t_len = probs.shape[0]
    if t_len == 0:
        return np.zeros((0, N_STRINGS), dtype=np.int8)
    if switch_penalty <= 0:
        return probs.argmax(axis=-1).astype(np.int8)
    cost = -np.log(np.clip(probs, 1e-6, 1.0))  # (T, S, C)
    best = cost[0].copy()
    back = np.zeros((t_len, N_STRINGS, N_CLASSES), dtype=np.int8)
    for t in range(1, t_len):
        stay = best  # same class, no penalty
        jump_from = best.argmin(axis=-1)  # (S,)
        jump = best[np.arange(N_STRINGS), jump_from][:, None] + switch_penalty
        take_jump = jump < stay
        back[t] = np.where(take_jump, jump_from[:, None], np.arange(N_CLASSES)[None, :])
        best = np.where(take_jump, jump, stay) + cost[t]
    path = np.zeros((t_len, N_STRINGS), dtype=np.int8)
    path[-1] = best.argmin(axis=-1)
    for t in range(t_len - 1, 0, -1):
        path[t - 1] = back[t][np.arange(N_STRINGS), path[t]]
    return path


def onset_frames(y: np.ndarray) -> np.ndarray:
    import librosa

    if y.size < HOP * 4:
        return np.zeros(0, dtype=int)
    return librosa.onset.onset_detect(y=y, sr=SR, hop_length=HOP, units="frames", backtrack=False)


def decode(
    probs: np.ndarray,
    opts: DecodeOptions = DecodeOptions(),
    onsets: np.ndarray | None = None,
) -> list[NoteEvent]:
    """Per-frame probabilities → note events (canonical string numbering)."""
    classes = viterbi_classes(probs, opts.switch_penalty)
    min_frames = max(1, int(round(opts.min_note_ms / 1000 * FPS)))
    onset_set = set(int(o) for o in onsets) if (onsets is not None and opts.split_on_onsets) else set()
    notes: list[NoteEvent] = []
    for s in range(N_STRINGS):
        for start, end, cls in _runs(classes[:, s]):
            for a, b in _split(start, end, onset_set, min_frames):
                if b - a < min_frames:
                    continue
                level = float(probs[a:b, s, cls].mean())
                if level < opts.min_prob:
                    continue
                notes.append(
                    NoteEvent(
                        onset_s=a * HOP / SR,
                        offset_s=b * HOP / SR,
                        pitch_midi=MODEL_STRING_OPEN_MIDI[s] + cls - 1,
                        velocity=level,
                        confidence=level,
                        string=model_string_to_canonical(s),
                        fret=cls - 1,
                    )
                )
    notes.sort(key=lambda n: (n.onset_s, n.pitch_midi))
    return notes


def _runs(seq: np.ndarray) -> list[tuple[int, int, int]]:
    """Maximal runs of a constant non-zero class as ``(start, end_exclusive, class)``."""
    out: list[tuple[int, int, int]] = []
    if seq.size == 0:
        return out
    change = np.flatnonzero(np.diff(seq)) + 1
    bounds = np.concatenate([[0], change, [seq.size]])
    for a, b in zip(bounds, bounds[1:], strict=False):
        cls = int(seq[a])
        if cls > 0:
            out.append((int(a), int(b), cls))
    return out


def _split(start: int, end: int, onsets: set[int], min_frames: int) -> list[tuple[int, int]]:
    """Cut a sustained run at onsets that fall well inside it (re-plucked same note)."""
    cuts = sorted(o for o in onsets if start + min_frames <= o <= end - min_frames)
    pieces: list[tuple[int, int]] = []
    a = start
    for c in cuts:
        if c - a >= min_frames:
            pieces.append((a, c))
            a = c
    pieces.append((a, end))
    return pieces
