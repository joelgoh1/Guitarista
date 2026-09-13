"""GuitarSet on disk: download, enumerate excerpts, cache CQT frames + labels, player folds.

Data lives outside the repo in ``$GUITARISTA_ML_DATA`` (default ``apps/ml/data``), which is
gitignored. GuitarSet is CC-BY-4.0 (Xi, Bittner, Pauwels, Ye, Bello — ISMIR 2018).
"""

from __future__ import annotations

import os
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from guitarista_ml.tabcnn.features import cqt_frames, load_mono
from guitarista_ml.tabcnn.labels import frame_labels, parse_jams_notes

ZENODO_RECORD = "3371780"
PARTS = {"annotation": "annotation", "mic": "audio_mono-mic", "mix": "audio_mono-pickup_mix"}
AUDIO_SUFFIX = {"mic": "_mic.wav", "mix": "_mix.wav"}
N_PLAYERS = 6


def data_home() -> Path:
    env = os.environ.get("GUITARISTA_ML_DATA")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "data"


def guitarset_dir(home: Path | None = None) -> Path:
    return (home or data_home()) / "guitarset"


def cache_dir(home: Path | None = None) -> Path:
    return (home or data_home()) / "cache" / "tabcnn"


@dataclass(frozen=True, slots=True)
class Excerpt:
    id: str
    player: int
    jams: Path
    audio: dict[str, Path]

    def cache_key(self, source: str) -> str:
        return f"{self.id}__{source}"


def fetch_guitarset(
    parts: Iterable[str] = ("annotation", "mic"),
    home: Path | None = None,
    on_progress: Callable[[str, float], None] | None = None,
) -> Path:
    """Download and unzip the requested parts (idempotent)."""
    root = guitarset_dir(home)
    root.mkdir(parents=True, exist_ok=True)
    for part in parts:
        name = PARTS[part]
        target = root / name
        if target.is_dir() and any(target.iterdir()):
            continue
        url = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/{name}.zip/content"
        archive = root / f"{name}.zip"

        def _hook(count: int, block: int, total: int, _part: str = part) -> None:
            if on_progress and total > 0:
                on_progress(_part, min(1.0, count * block / total))

        urllib.request.urlretrieve(url, archive, reporthook=_hook)  # noqa: S310 (fixed https URL)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
        archive.unlink()
    return root


def _find(root: Path, suffix: str) -> dict[str, Path]:
    return {p.name[: -len(suffix)]: p for p in root.rglob(f"*{suffix}") if not p.name.startswith(".")}


def list_excerpts(home: Path | None = None, sources: Sequence[str] = ("mic",)) -> list[Excerpt]:
    root = guitarset_dir(home)
    jams = _find(root / PARTS["annotation"], ".jams")
    if not jams:
        raise FileNotFoundError(f"no GuitarSet annotations under {root}; run `guitarista-ml guitarset-fetch`")
    audio = {src: _find(root / PARTS[src], AUDIO_SUFFIX[src]) for src in sources}
    out: list[Excerpt] = []
    for eid in sorted(jams):
        files = {src: audio[src][eid] for src in sources if eid in audio[src]}
        if len(files) != len(sources):
            continue
        out.append(Excerpt(eid, int(eid.split("_")[0]), jams[eid], files))
    return out


def fold_split(excerpts: Sequence[Excerpt], fold: int) -> tuple[list[Excerpt], list[Excerpt]]:
    """Hold out one player (the TabCNN protocol)."""
    if not 0 <= fold < N_PLAYERS:
        raise ValueError(f"fold must be 0..{N_PLAYERS - 1}")
    train = [e for e in excerpts if e.player != fold]
    val = [e for e in excerpts if e.player == fold]
    return train, val


def cache_path(excerpt: Excerpt, source: str, home: Path | None = None) -> Path:
    return cache_dir(home) / f"{excerpt.cache_key(source)}.npz"


def build_cache(
    excerpts: Sequence[Excerpt],
    sources: Sequence[str] = ("mic",),
    home: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """CQT frames (float16) + per-frame labels (int8) per excerpt and audio source."""
    cache_dir(home).mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    todo = [(e, s) for e in excerpts for s in sources]
    for i, (excerpt, source) in enumerate(todo):
        path = cache_path(excerpt, source, home)
        if not path.exists():
            frames = cqt_frames(load_mono(excerpt.audio[source]))
            labels = frame_labels(parse_jams_notes(excerpt.jams), frames.shape[0])
            np.savez(path, frames=frames.astype(np.float16), labels=labels, player=excerpt.player)
        paths.append(path)
        if on_progress:
            on_progress(i + 1, len(todo))
    return paths


def load_cached(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path) as z:
        return z["frames"].astype(np.float32), z["labels"].astype(np.int8)
