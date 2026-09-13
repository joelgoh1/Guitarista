"""GuitarSet JAMS → per-frame TabCNN targets, and the string-order conversion to canonical tabs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from guitarista_ml.tabcnn.features import (
    HOP,
    MAX_FRET,
    MODEL_STRING_OPEN_MIDI,
    N_STRINGS,
    SR,
)


@dataclass(frozen=True, slots=True)
class StringNote:
    string_idx: int  # model order, 0 = low E
    onset_s: float
    duration_s: float
    midi: float


def model_string_to_canonical(string_idx: int) -> int:
    """Model index 0 (low E) → canonical string 6; index 5 (high E) → string 1."""
    if not 0 <= string_idx < N_STRINGS:
        raise ValueError(f"string index {string_idx} outside 0..{N_STRINGS - 1}")
    return N_STRINGS - string_idx


def canonical_to_model_string(string: int) -> int:
    """Canonical string 1 (high E) → model index 5; string 6 (low E) → index 0."""
    if not 1 <= string <= N_STRINGS:
        raise ValueError(f"string {string} outside 1..{N_STRINGS}")
    return N_STRINGS - string


def parse_jams_notes(path: Path) -> list[StringNote]:
    """Read the six ``note_midi`` annotations without depending on the ``jams`` package."""
    doc = json.loads(Path(path).read_text())
    notes: list[StringNote] = []
    for ann in doc.get("annotations", []):
        if ann.get("namespace") != "note_midi":
            continue
        source = (ann.get("annotation_metadata") or {}).get("data_source")
        string_idx = int(source)
        for obs in ann.get("data", []):
            notes.append(
                StringNote(string_idx, float(obs["time"]), float(obs["duration"]), float(obs["value"]))
            )
    strings = {n.string_idx for n in notes}
    if not strings <= set(range(N_STRINGS)):
        raise ValueError(f"{path}: unexpected string indices {sorted(strings)}")
    return notes


def fret_class(midi: float, string_idx: int) -> int:
    """Class index for a sounding note, or 0 if it is off the fretboard for that string."""
    fret = int(round(midi)) - MODEL_STRING_OPEN_MIDI[string_idx]
    return fret + 1 if 0 <= fret <= MAX_FRET else 0


def frame_labels(notes: list[StringNote], n_frames: int) -> np.ndarray:
    """``(T, 6)`` int8 class per string per frame (0 = silent), sampled at frame centres."""
    labels = np.zeros((n_frames, N_STRINGS), dtype=np.int8)
    times = np.arange(n_frames) * HOP / SR
    for n in notes:
        cls = fret_class(n.midi, n.string_idx)
        if cls == 0:
            continue
        lo = int(np.searchsorted(times, n.onset_s, side="left"))
        hi = int(np.searchsorted(times, n.onset_s + n.duration_s, side="left"))
        if hi > lo:
            labels[lo:hi, n.string_idx] = cls
    return labels


def shift_labels(labels: np.ndarray, semitones: int) -> np.ndarray | None:
    """Labels for the same audio pitch-shifted by ``semitones`` (frets move with the pitch).

    Returns ``None`` when any sounding note would leave the 0..MAX_FRET range.
    """
    sounding = labels > 0
    shifted = labels.astype(np.int16) + semitones * sounding
    if np.any((shifted < 1) & sounding) or np.any(shifted > MAX_FRET + 1):
        return None
    return shifted.astype(np.int8)
