"""Score TabCNN (and basic-pitch's pitch output) against GuitarSet ground truth."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from guitarista_ml.tabcnn.data import Excerpt, cache_path, fold_split, list_excerpts, load_cached
from guitarista_ml.tabcnn.features import FPS, cqt_frames, load_mono
from guitarista_ml.tabcnn.infer import DEFAULT_WEIGHTS, DecodeOptions, TabCNNPredictor, onset_frames, viterbi_classes
from guitarista_ml.tabcnn.labels import frame_labels, parse_jams_notes
from guitarista_ml.tabcnn.metrics import _prf, compute_metrics, pitch_binary


def _ground_truth(excerpt: Excerpt, n_frames: int) -> np.ndarray:
    return frame_labels(parse_jams_notes(excerpt.jams), n_frames)


def evaluate_tabcnn(
    excerpts: Sequence[Excerpt],
    weights: Path = DEFAULT_WEIGHTS,
    source: str = "mic",
    switch_penalty: float = 2.0,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, object]:
    predictor = TabCNNPredictor(weights)
    preds, gts, per_excerpt = [], [], {}
    for i, ex in enumerate(excerpts):
        cached = cache_path(ex, source)
        if cached.exists():
            frames, gt = load_cached(cached)
        else:
            frames = cqt_frames(load_mono(ex.audio[source]))
            gt = _ground_truth(ex, frames.shape[0])
        probs = predictor.predict_frames(frames)
        argmax = viterbi_classes(probs, 0.0)
        smoothed = viterbi_classes(probs, switch_penalty)
        per_excerpt[ex.id] = {"argmax": compute_metrics(argmax, gt).to_dict(), "viterbi": compute_metrics(smoothed, gt).to_dict()}
        preds.append((argmax, smoothed))
        gts.append(gt)
        if on_progress:
            on_progress(i + 1, len(excerpts))
    gt_all = np.concatenate(gts)
    return {
        "model": "tabcnn",
        "weights": str(weights),
        "excerpts": len(excerpts),
        "frames": int(gt_all.shape[0]),
        "argmax": compute_metrics(np.concatenate([p[0] for p in preds]), gt_all).to_dict(),
        "viterbi": compute_metrics(np.concatenate([p[1] for p in preds]), gt_all).to_dict(),
        "per_excerpt": per_excerpt,
    }


def evaluate_basic_pitch(
    excerpts: Sequence[Excerpt],
    source: str = "mic",
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, object]:
    """Frame-level multipitch P/R/F of basic-pitch notes against the GuitarSet tab (pitch only)."""
    from guitarista_ml.io import quiet_stdout
    from guitarista_ml.schema import TranscribeOptions
    from guitarista_ml.transcribe import basic_pitch_notes

    opts = TranscribeOptions()
    preds, gts = [], []
    for i, ex in enumerate(excerpts):
        y = load_mono(ex.audio[source])
        n_frames = cqt_frames(y).shape[0]
        gt = pitch_binary(_ground_truth(ex, n_frames))
        with quiet_stdout():
            notes = basic_pitch_notes(ex.audio[source], opts)
        act = np.zeros_like(gt)
        for n in notes:
            lo, hi = int(round(n.onset_s * FPS)), int(round(n.offset_s * FPS))
            col = n.pitch_midi - 40
            if 0 <= col < act.shape[1]:
                act[lo:max(hi, lo + 1), col] = True
        preds.append(act)
        gts.append(gt)
        if on_progress:
            on_progress(i + 1, len(excerpts))
    p, r, f = _prf(np.concatenate(preds), np.concatenate(gts))
    return {"model": "basic-pitch", "excerpts": len(excerpts), "pitch_precision": round(p, 4), "pitch_recall": round(r, 4), "pitch_f1": round(f, 4)}


def held_out(fold: int, source: str = "mic", limit: int | None = None) -> list[Excerpt]:
    _, val = fold_split(list_excerpts(sources=(source,)), fold)
    return val[:limit] if limit else val
