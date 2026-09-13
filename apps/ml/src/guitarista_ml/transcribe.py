"""Polyphonic transcription of a wav file: basic-pitch (pitch only) or TabCNN (string + fret)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from guitarista_ml.io import CliError, emit_progress, quiet_stdout
from guitarista_ml.schema import BASIC_PITCH_MODEL, NoteEvent, TranscribeOptions, TranscribeSummary, TranscriptionResult


def _check_wav(path: Path) -> None:
    if not path.is_file():
        raise CliError(f"input file not found: {path}", type="invalid_input", exit_code=2)
    if path.suffix.lower() != ".wav":
        raise CliError(
            f"only .wav input is accepted (got {path.suffix or 'no extension'}); convert with ffmpeg first",
            type="invalid_input",
            exit_code=2,
        )


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    try:
        y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:  # soundfile raises RuntimeError/ValueError on bad files
        raise CliError(f"could not read wav: {exc}", type="invalid_input", exit_code=2) from exc
    if y.shape[0] == 0:
        raise CliError("wav file is empty", type="invalid_input", exit_code=2)
    return y.mean(axis=1), int(sr)


def _estimate_beats(y: np.ndarray, sr: int) -> tuple[float | None, list[float]]:
    """Global tempo plus beat times; the caller aligns its grid to the beats, not just the bpm."""
    import librosa

    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    except Exception as exc:
        logging.warning("tempo estimation failed: %s", exc)
        return None, []
    value = float(np.atleast_1d(tempo)[0])
    beats_s = [round(float(b), 4) for b in np.atleast_1d(beats) if np.isfinite(b)]
    return (value if np.isfinite(value) and value > 0 else None), beats_s


def basic_pitch_notes(in_path: Path, opts: TranscribeOptions) -> list[NoteEvent]:
    emit_progress(0.08, "model")
    try:
        with quiet_stdout():
            from basic_pitch import ICASSP_2022_MODEL_PATH
            from basic_pitch.inference import Model, predict
            model = Model(ICASSP_2022_MODEL_PATH)
    except Exception as exc:
        raise CliError(f"basic-pitch model failed to load: {exc!r}", type="model_load", exit_code=4) from exc

    emit_progress(0.15, "predict")
    t0 = time.perf_counter()
    try:
        with quiet_stdout():
            _, _, note_events = predict(
                str(in_path),
                model,
                onset_threshold=opts.onset_threshold,
                frame_threshold=opts.frame_threshold,
                minimum_note_length=opts.min_note_ms,
                minimum_frequency=opts.fmin,
                maximum_frequency=opts.fmax,
                multiple_pitch_bends=False,
                melodia_trick=True,
            )
    except Exception as exc:
        raise CliError(f"basic-pitch inference failed: {exc!r}", type="inference", exit_code=4) from exc
    logging.info("basic-pitch predict took %.2fs", time.perf_counter() - t0)

    notes = []
    for start, end, pitch, amplitude, bends in note_events:
        level = float(min(1.0, max(0.0, amplitude)))
        notes.append(
            NoteEvent(
                onset_s=float(start),
                offset_s=float(end),
                pitch_midi=int(pitch),
                velocity=level,
                pitch_bend=[int(b) for b in bends] if bends is not None else None,
                confidence=level,
            )
        )
    return notes


def tabcnn_notes(y: np.ndarray, sr: int, opts: TranscribeOptions) -> list[NoteEvent]:
    """String/fret notes from the shipped TabCNN (onnxruntime only; see ``tabcnn/infer.py``)."""
    from guitarista_ml.tabcnn.features import SR
    from guitarista_ml.tabcnn.infer import DecodeOptions, TabCNNPredictor, decode, onset_frames, weights_available

    if not weights_available():
        raise CliError(
            "TabCNN weights are not installed (apps/ml/src/guitarista_ml/models/tabcnn.onnx); "
            "train with `guitarista-ml tabcnn-train` and export with `tabcnn-export`",
            type="model_load",
            exit_code=4,
        )
    if sr != SR:
        import librosa

        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    emit_progress(0.08, "model")
    try:
        predictor = TabCNNPredictor()
    except Exception as exc:
        raise CliError(f"TabCNN model failed to load: {exc!r}", type="model_load", exit_code=4) from exc
    emit_progress(0.15, "predict")
    t0 = time.perf_counter()
    try:
        probs = predictor.predict_audio(y)
        emit_progress(0.7, "decode")
        notes = decode(probs, DecodeOptions(min_note_ms=opts.min_note_ms), onsets=onset_frames(y))
    except Exception as exc:
        raise CliError(f"TabCNN inference failed: {exc!r}", type="inference", exit_code=4) from exc
    logging.info("tabcnn predict+decode took %.2fs", time.perf_counter() - t0)
    lo, hi = opts.fmin, opts.fmax
    if lo is not None or hi is not None:
        import librosa

        notes = [n for n in notes if (lo is None or librosa.midi_to_hz(n.pitch_midi) >= lo) and (hi is None or librosa.midi_to_hz(n.pitch_midi) <= hi)]
    return notes


def transcribe(in_path: Path, opts: TranscribeOptions) -> TranscriptionResult:
    _check_wav(in_path)
    emit_progress(0.02, "load")
    y, sr = _load_audio(in_path)
    duration_s = len(y) / sr

    if opts.model == "tabcnn":
        from guitarista_ml.tabcnn.infer import TABCNN_MODEL

        notes, model_name = tabcnn_notes(y, sr, opts), TABCNN_MODEL
    else:
        notes, model_name = basic_pitch_notes(in_path, opts), BASIC_PITCH_MODEL
    emit_progress(0.85, "notes")
    notes.sort(key=lambda n: (n.onset_s, n.pitch_midi))

    tempo_bpm: float | None = None
    beats_s: list[float] = []
    if opts.estimate_tempo:
        emit_progress(0.9, "tempo")
        tempo_bpm, beats_s = _estimate_beats(y, sr)

    return TranscriptionResult(
        notes=notes,
        tempo_bpm=tempo_bpm,
        beats_s=beats_s,
        source_audio=str(in_path),
        duration_s=round(duration_s, 4),
        model=model_name,
    )


def transcribe_to_file(in_path: Path, out_path: Path, opts: TranscribeOptions) -> TranscribeSummary:
    result = transcribe(in_path, opts)
    emit_progress(0.97, "write")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1))
    emit_progress(1.0, "done")
    return {
        "ok": True,
        "out": str(out_path),
        "note_count": len(result.notes),
        "tempo_bpm": result.tempo_bpm,
    }
