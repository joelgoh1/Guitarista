"""Frame-level tablature metrics, as defined by the TabCNN paper (``Metrics.py`` in tab-cnn).

Inputs are ``(T, 6)`` integer class arrays (0 = string silent, k = fret k-1).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from guitarista_ml.tabcnn.features import MODEL_STRING_OPEN_MIDI, N_STRINGS

_PITCH_LO = 40
_PITCH_HI = 64 + 19  # highest class on the top string


@dataclass(frozen=True, slots=True)
class TabMetrics:
    pitch_precision: float
    pitch_recall: float
    pitch_f1: float
    tab_precision: float
    tab_recall: float
    tab_f1: float
    tab_disambiguation: float
    """TDR = tab precision / pitch precision: how often a correct pitch is on the right string."""

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in asdict(self).items()}


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _f1(p: float, r: float) -> float:
    return _safe_div(2 * p * r, p + r)


def tab_binary(classes: np.ndarray) -> np.ndarray:
    """``(T, 6, 20)`` one-hot of sounding frets (the silent class is dropped)."""
    classes = np.asarray(classes)
    out = np.zeros((*classes.shape, 20), dtype=bool)
    t, s = np.nonzero(classes > 0)
    out[t, s, classes[t, s] - 1] = True
    return out


def pitch_binary(classes: np.ndarray) -> np.ndarray:
    """``(T, 44)`` multi-pitch activation implied by the tab (MIDI 40..83)."""
    classes = np.asarray(classes)
    out = np.zeros((classes.shape[0], _PITCH_HI - _PITCH_LO + 1), dtype=bool)
    for s in range(N_STRINGS):
        t = np.nonzero(classes[:, s] > 0)[0]
        midi = classes[t, s] - 1 + MODEL_STRING_OPEN_MIDI[s]
        out[t, midi - _PITCH_LO] = True
    return out


def _prf(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float, float]:
    hit = float(np.sum(pred & gt))
    p = _safe_div(hit, float(pred.sum()))
    r = _safe_div(hit, float(gt.sum()))
    return p, r, _f1(p, r)


def compute_metrics(pred: np.ndarray, gt: np.ndarray) -> TabMetrics:
    if pred.shape != gt.shape:
        raise ValueError(f"shape mismatch {pred.shape} vs {gt.shape}")
    pp, pr, pf = _prf(pitch_binary(pred), pitch_binary(gt))
    tp, tr, tf = _prf(tab_binary(pred), tab_binary(gt))
    return TabMetrics(pp, pr, pf, tp, tr, tf, _safe_div(tp, pp))
