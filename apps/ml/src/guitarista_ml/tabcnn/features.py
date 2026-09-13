"""CQT front-end shared by training and inference so the two can never drift apart."""

from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 22050
HOP = 512
N_BINS = 192
BINS_PER_OCTAVE = 24
FPS = SR / HOP  # ≈ 43.07 frames per second
DB_FLOOR = -80.0

MODEL_STRING_OPEN_MIDI = (40, 45, 50, 55, 59, 64)
"""Open-string pitches in *model* order: index 0 = low E. Canonical tab order is the reverse."""
N_STRINGS = len(MODEL_STRING_OPEN_MIDI)
MAX_FRET = 19
N_CLASSES = MAX_FRET + 2
"""Per string: class 0 = not sounding, class k = fret k-1 (0..19)."""


def frame_time(index: int | np.ndarray) -> np.ndarray:
    return np.asarray(index) * HOP / SR


def load_mono(path: Path) -> np.ndarray:
    import soundfile as sf

    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        import librosa

        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    return y.astype(np.float32)


def cqt_frames(y: np.ndarray) -> np.ndarray:
    """``(T, N_BINS)`` log-magnitude CQT, standardised per clip.

    The original TabCNN fed raw magnitudes; log scaling plus per-clip standardisation removes
    the level dependence, which matters once inputs come from Demucs stems and phone recordings.
    """
    import librosa

    if y.size == 0:
        return np.zeros((0, N_BINS), dtype=np.float32)
    y = librosa.util.normalize(y.astype(np.float32))
    mag = np.abs(librosa.cqt(y, sr=SR, hop_length=HOP, n_bins=N_BINS, bins_per_octave=BINS_PER_OCTAVE))
    db = librosa.amplitude_to_db(mag, ref=np.max, top_db=-DB_FLOOR)
    std = float(db.std()) or 1.0
    return ((db - db.mean()) / std).T.astype(np.float32)


def context_windows(frames: np.ndarray, window: int) -> np.ndarray:
    """Stack ``window`` frames centred on each frame → ``(T, N_BINS, window)`` (zero padded)."""
    if window < 1 or window % 2 == 0:
        raise ValueError("context window must be a positive odd number")
    half = window // 2
    padded = np.pad(frames, [(half, half), (0, 0)])
    idx = np.arange(frames.shape[0])[:, None] + np.arange(window)[None, :]
    return np.transpose(padded[idx], (0, 2, 1))
