"""Unit tests for the TabCNN package: features, labels, metrics, decoding, and (with the train
extra) a torch → ONNX round trip on random weights. No dataset needed."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from guitarista_ml.tabcnn.features import (
    FPS,
    MODEL_STRING_OPEN_MIDI,
    N_BINS,
    N_CLASSES,
    N_STRINGS,
    SR,
    context_windows,
    cqt_frames,
)
from guitarista_ml.tabcnn.infer import DecodeOptions, _runs, decode, viterbi_classes
from guitarista_ml.tabcnn.labels import (
    StringNote,
    canonical_to_model_string,
    frame_labels,
    fret_class,
    model_string_to_canonical,
    parse_jams_notes,
    shift_labels,
)
from guitarista_ml.tabcnn.metrics import compute_metrics, pitch_binary, tab_binary

HAS_TORCH = importlib.util.find_spec("torch") is not None


def test_cqt_frames_shape_and_scale() -> None:
    t = np.arange(SR * 2) / SR
    y = np.sin(2 * np.pi * 110.0 * t).astype(np.float32)
    frames = cqt_frames(y)
    assert frames.shape[1] == N_BINS and abs(frames.shape[0] - 2 * FPS) <= 2
    assert abs(float(frames.mean())) < 1e-3 and abs(float(frames.std()) - 1.0) < 1e-3
    assert cqt_frames(np.zeros(0, dtype=np.float32)).shape == (0, N_BINS)
    # A2 = 110 Hz sits ~42 bins above C1 at 24 bins/octave; that bin must be the loudest.
    peak = int(frames.mean(axis=0).argmax())
    assert abs(peak - 42) <= 1, peak


def test_context_windows_centred_and_padded() -> None:
    frames = np.arange(5 * N_BINS, dtype=np.float32).reshape(5, N_BINS)
    win = context_windows(frames, 3)
    assert win.shape == (5, N_BINS, 3)
    assert np.all(win[0, :, 0] == 0) and np.all(win[0, :, 1] == frames[0]) and np.all(win[0, :, 2] == frames[1])
    assert np.all(win[4, :, 2] == 0)
    with pytest.raises(ValueError):
        context_windows(frames, 4)


def test_string_order_pin() -> None:
    """Model index 0 is the low E (MIDI 40); canonical string 1 is the high E. Never flip this silently."""
    assert MODEL_STRING_OPEN_MIDI[0] == 40 and MODEL_STRING_OPEN_MIDI[5] == 64
    assert model_string_to_canonical(0) == 6 and model_string_to_canonical(5) == 1
    assert [canonical_to_model_string(model_string_to_canonical(i)) for i in range(6)] == list(range(6))
    with pytest.raises(ValueError):
        model_string_to_canonical(6)


def test_fret_class_and_frame_labels() -> None:
    assert fret_class(40.0, 0) == 1 and fret_class(59.4, 0) == 20 and fret_class(60.0, 0) == 0
    assert fret_class(39.0, 0) == 0  # below the open string
    notes = [StringNote(0, 0.0, 0.5, 40.2), StringNote(5, 0.25, 0.5, 69.0)]  # E2 open, A4 = fret 5
    labels = frame_labels(notes, int(FPS))
    assert labels.shape == (int(FPS), N_STRINGS)
    assert labels[0, 0] == 1 and labels[int(0.4 * FPS), 0] == 1 and labels[int(0.6 * FPS), 0] == 0
    assert labels[int(0.3 * FPS), 5] == 6 and labels[0, 5] == 0


def test_parse_jams_reads_note_midi_by_string(tmp_path: Path) -> None:
    doc = {
        "annotations": [
            {"namespace": "pitch_contour", "annotation_metadata": {"data_source": "0"}, "data": []},
            {
                "namespace": "note_midi",
                "annotation_metadata": {"data_source": "3"},
                "data": [{"time": 1.0, "duration": 0.5, "value": 55.02, "confidence": None}],
            },
            {"namespace": "beat_position", "annotation_metadata": {"data_source": ""}, "data": []},
        ]
    }
    path = tmp_path / "x.jams"
    path.write_text(json.dumps(doc))
    notes = parse_jams_notes(path)
    assert notes == [StringNote(3, 1.0, 0.5, 55.02)]


def test_shift_labels_moves_frets_and_rejects_out_of_range() -> None:
    labels = np.array([[1, 0, 5, 0, 0, 20]], dtype=np.int8)
    up = shift_labels(labels, 1)
    assert up is None  # class 20 (fret 19) cannot go higher
    down = shift_labels(labels, -1)
    assert down is None  # class 1 (open) cannot go lower
    mid = np.array([[2, 0, 5, 0, 0, 19]], dtype=np.int8)
    assert shift_labels(mid, 1).tolist() == [[3, 0, 6, 0, 0, 20]]
    assert shift_labels(mid, -1).tolist() == [[1, 0, 4, 0, 0, 18]]


def test_metrics_perfect_and_string_confusion() -> None:
    gt = np.zeros((4, N_STRINGS), dtype=np.int8)
    gt[:, 5] = 1  # open high E (MIDI 64) for four frames
    perfect = compute_metrics(gt, gt)
    assert perfect.tab_f1 == 1.0 and perfect.pitch_f1 == 1.0 and perfect.tab_disambiguation == 1.0
    wrong_string = np.zeros_like(gt)
    wrong_string[:, 4] = 6  # B string fret 5 = also MIDI 64
    m = compute_metrics(wrong_string, gt)
    assert m.pitch_f1 == 1.0 and m.tab_f1 == 0.0 and m.tab_disambiguation == 0.0
    assert tab_binary(gt).sum() == 4 and pitch_binary(gt)[:, 64 - 40].all()


def test_viterbi_smooths_single_frame_glitches() -> None:
    t_len = 20
    probs = np.full((t_len, N_STRINGS, N_CLASSES), 0.01, dtype=np.float32)
    probs[:, :, 0] = 0.9
    probs[5:15, 0, 6] = 0.8  # low E fret 5 for 10 frames
    probs[5:15, 0, 0] = 0.05
    probs[10, 0, 6], probs[10, 0, 7] = 0.3, 0.6  # one-frame flicker to fret 6
    argmax = viterbi_classes(probs, 0.0)
    smooth = viterbi_classes(probs, 2.0)
    assert argmax[10, 0] == 7 and smooth[10, 0] == 6
    assert list(smooth[5:15, 0]) == [6] * 10 and smooth[:5, 0].max() == 0
    assert _runs(smooth[:, 0]) == [(5, 15, 6)]


def test_decode_emits_canonical_strings_and_splits_on_onsets() -> None:
    t_len = 60
    probs = np.full((t_len, N_STRINGS, N_CLASSES), 0.001, dtype=np.float32)
    probs[:, :, 0] = 0.95
    probs[0:40, 5, 1] = 0.9  # high E open for 40 frames
    probs[0:40, 5, 0] = 0.02
    notes = decode(probs, DecodeOptions(min_note_ms=50), onsets=np.array([20]))
    assert [(n.string, n.fret, n.pitch_midi) for n in notes] == [(1, 0, 64), (1, 0, 64)]
    assert notes[0].onset_s == 0.0 and abs(notes[0].offset_s - 20 / FPS) < 1e-9
    assert abs(notes[1].onset_s - 20 / FPS) < 1e-9
    assert 0.8 < notes[0].confidence <= 1.0 and notes[0].velocity == notes[0].confidence
    # a one-frame blip is shorter than min_note_ms and must be dropped
    probs[50:51, 0, 3] = 0.9
    assert len(decode(probs, DecodeOptions(min_note_ms=58, switch_penalty=0.0), onsets=None)) == 1


@pytest.mark.skipif(not HAS_TORCH, reason="train extra not installed")
def test_model_shapes_and_onnx_round_trip(tmp_path: Path) -> None:
    import torch

    from guitarista_ml.tabcnn.export import export_onnx
    from guitarista_ml.tabcnn.infer import TabCNNPredictor
    from guitarista_ml.tabcnn.model import CONFIGS, TabCNN, count_parameters, string_cross_entropy
    from guitarista_ml.tabcnn.train import save_checkpoint

    for cfg in CONFIGS.values():
        model = TabCNN(cfg)
        out = model(torch.zeros(3, 1, N_BINS, cfg.context))
        assert out.shape == (3, N_STRINGS, N_CLASSES)
        loss = string_cross_entropy(out, torch.zeros(3, N_STRINGS, dtype=torch.long))
        assert float(loss) > 0
        assert count_parameters(model) < 3_000_000, (cfg.name, count_parameters(model))

    cfg = CONFIGS["baseline"]
    model = TabCNN(cfg)
    ckpt = tmp_path / "w.pt"
    save_checkpoint(model, cfg, ckpt)
    onnx_path = tmp_path / "m.onnx"
    info = export_onnx(ckpt, onnx_path)
    assert info["max_abs_diff"] < 1e-4 and onnx_path.stat().st_size < 10_000_000

    predictor = TabCNNPredictor(onnx_path)
    assert predictor.context == cfg.context
    frames = np.random.randn(30, N_BINS).astype(np.float32)
    probs = predictor.predict_frames(frames)
    assert probs.shape == (30, N_STRINGS, N_CLASSES)
    assert np.allclose(probs.sum(-1), 1.0, atol=1e-4)


@pytest.mark.skipif(not HAS_TORCH, reason="train extra not installed")
def test_frames_batches_gather_context_and_shift_labels(tmp_path: Path) -> None:
    import random

    from guitarista_ml.tabcnn.train import _Frames

    paths = []
    for e in range(2):
        frames = np.random.randn(10 + e, N_BINS).astype(np.float32)
        labels = np.zeros((10 + e, N_STRINGS), dtype=np.int8)
        labels[:, 0] = 5  # low E fret 4 throughout
        p = tmp_path / f"e{e}.npz"
        np.savez(p, frames=frames.astype(np.float16), labels=labels, player=e)
        paths.append(p)
    data = _Frames(paths, context=5)
    assert len(data) == 21 and data.n_excerpts == 2
    x, y = data.batch([0, 10, 20], augment=False, rng=random.Random(0))
    assert x.shape == (3, 1, N_BINS, 5) and y.tolist()[0][0] == 5
    assert np.all(x[0, 0, :, :2] == 0)  # first frame of excerpt 0: left context is padding
    assert np.all(x[2, 0, :, 3:] == 0)  # last frame of excerpt 1: right context is padding
    xe, ye = data.excerpt_windows(1)
    assert xe.shape == (11, 1, N_BINS, 5) and ye.shape == (11, N_STRINGS)
    rng = random.Random(1)
    seen = set()
    for _ in range(20):
        _, ya = data.batch([0, 1, 2], augment=True, rng=rng)
        seen.add(int(ya[0, 0]))
    assert seen <= {4, 5, 6} and len(seen) > 1
