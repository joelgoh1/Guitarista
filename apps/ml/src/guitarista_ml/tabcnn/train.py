"""Train TabCNN on GuitarSet (``train`` extra). Player-wise folds as in the paper.

Augmentation happens on the log-CQT itself: a ±1 semitone pitch shift is a 2-bin roll along the
frequency axis (24 bins/octave) with the fret labels shifted to match, plus mild Gaussian noise.
"""

from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from guitarista_ml.tabcnn.data import Excerpt, build_cache, fold_split, list_excerpts, load_cached
from guitarista_ml.tabcnn.features import BINS_PER_OCTAVE, N_BINS
from guitarista_ml.tabcnn.labels import shift_labels
from guitarista_ml.tabcnn.metrics import TabMetrics, compute_metrics
from guitarista_ml.tabcnn.model import CONFIGS, TabCNN, TabCNNConfig, count_parameters, string_cross_entropy

SEMITONE_BINS = BINS_PER_OCTAVE // 12


@dataclass(slots=True)
class TrainOptions:
    config: str = "improved"
    fold: int | None = 5
    """Held-out player; ``None`` trains on everyone (for the shipped weights)."""
    sources: tuple[str, ...] = ("mic",)
    epochs: int = 30
    batch_size: int = 256
    lr: float = 1e-3
    label_smoothing: float = 0.05
    patience: int = 5
    augment: bool = True
    limit_excerpts: int | None = None
    """Debug: use only this many excerpts."""
    seed: int = 0
    device: str = "auto"
    out_dir: Path = field(default_factory=lambda: Path("runs"))
    data_home: Path | None = None


class _Frames:
    """All cached excerpts in RAM as one padded array; batches are a single fancy-index gather."""

    def __init__(self, paths: Sequence[Path], context: int) -> None:
        self.context = context
        self.half = context // 2
        frames, labels, starts, self.bounds = [], [], [], []
        offset = 0
        for p in paths:
            f, lab = load_cached(p)
            padded = np.pad(f, [(self.half, self.half), (0, 0)])
            frames.append(padded)
            labels.append(lab)
            starts.append(offset + np.arange(lab.shape[0]))
            self.bounds.append((offset, lab.shape[0]))
            offset += padded.shape[0]
        self.frames = np.concatenate(frames) if frames else np.zeros((0, N_BINS), np.float32)
        self.labels = np.concatenate(labels) if labels else np.zeros((0, 6), np.int8)
        self.starts = np.concatenate(starts) if starts else np.zeros(0, np.int64)
        self.window = np.arange(context)

    def __len__(self) -> int:
        return int(self.starts.shape[0])

    def windows(self, idx: np.ndarray) -> np.ndarray:
        """``(B, 1, N_BINS, context)`` for sample indices ``idx``."""
        rows = self.starts[idx][:, None] + self.window[None, :]
        return np.ascontiguousarray(np.transpose(self.frames[rows], (0, 2, 1)))[:, None, :, :]

    def batch(self, idx: Sequence[int], augment: bool, rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
        idx = np.asarray(idx)
        x = self.windows(idx)
        y = self.labels[idx].astype(np.int64)
        if augment:
            shift = rng.choice((-1, 0, 0, 1))
            if shift:
                shifted = shift_labels(y, shift)  # None if any sample cannot move
                if shifted is None:
                    ok = np.array([shift_labels(row[None, :], shift) is not None for row in y])
                else:
                    ok = np.ones(len(y), dtype=bool)
                if ok.any():
                    sub = np.roll(x[ok], shift * SEMITONE_BINS, axis=2)
                    floor = x[ok].min(axis=(2, 3), keepdims=True)
                    if shift > 0:
                        sub[:, :, : shift * SEMITONE_BINS] = floor
                    else:
                        sub[:, :, shift * SEMITONE_BINS :] = floor
                    x[ok] = sub
                    y[ok] = np.where(y[ok] > 0, y[ok] + shift, 0)
            noisy = np.random.random(len(y)) < 0.5
            if noisy.any():
                x[noisy] += np.random.normal(0.0, 0.1, size=x[noisy].shape).astype(np.float32)
        return x, y

    def excerpt_windows(self, e: int) -> tuple[np.ndarray, np.ndarray]:
        offset, n = self.bounds[e]
        idx = np.arange(n) + sum(b[1] for b in self.bounds[:e])
        return self.windows(idx), self.labels[idx]

    @property
    def n_excerpts(self) -> int:
        return len(self.bounds)


def pick_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    return "mps" if torch.backends.mps.is_available() else "cpu"


def evaluate_model(model, data: _Frames, device: str, batch: int = 1024) -> TabMetrics:  # noqa: ANN001
    import torch

    model.eval()
    preds, gts = [], []
    with torch.no_grad():
        for e in range(data.n_excerpts):
            x, lab = data.excerpt_windows(e)
            out = []
            for i in range(0, x.shape[0], batch):
                logits = model(torch.from_numpy(x[i : i + batch]).to(device))
                out.append(logits.argmax(-1).cpu().numpy())
            preds.append(np.concatenate(out))
            gts.append(lab)
    return compute_metrics(np.concatenate(preds), np.concatenate(gts))


def train(opts: TrainOptions, on_progress: Callable[[float, str], None] | None = None) -> dict[str, object]:
    import torch

    cfg = CONFIGS[opts.config]
    torch.manual_seed(opts.seed)
    rng = random.Random(opts.seed)
    np.random.seed(opts.seed)

    excerpts = list_excerpts(opts.data_home, opts.sources)
    if opts.limit_excerpts and opts.limit_excerpts < len(excerpts):
        stride = len(excerpts) / opts.limit_excerpts  # spread over players, not just player 0
        excerpts = [excerpts[int(i * stride)] for i in range(opts.limit_excerpts)]
    if opts.fold is None:
        train_ex, val_ex = list(excerpts), []
    else:
        train_ex, val_ex = fold_split(excerpts, opts.fold)
    if not train_ex:
        raise ValueError("no training excerpts found")

    def _cache_progress(done: int, total: int) -> None:
        if on_progress:
            on_progress(0.15 * done / total, f"cache {done}/{total}")

    cache_paths = build_cache([*train_ex, *val_ex], opts.sources, opts.data_home, _cache_progress)
    n_train = len(train_ex) * len(opts.sources)
    train_data = _Frames(cache_paths[:n_train], cfg.context)
    val_data = _Frames(cache_paths[n_train:], cfg.context) if val_ex else None

    device = pick_device(opts.device)
    model = TabCNN(cfg).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=opts.lr) if cfg.name != "baseline" else torch.optim.Adadelta(model.parameters())
    steps_per_epoch = math.ceil(len(train_data) / opts.batch_size)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=opts.epochs * steps_per_epoch) if cfg.name != "baseline" else None

    run_dir = opts.out_dir / f"{cfg.name}-{time.strftime('%Y%m%d-%H%M%S')}-fold{opts.fold if opts.fold is not None else 'all'}"
    run_dir.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, object]] = []
    best_f1, best_epoch, bad_epochs = -math.inf, -1, 0
    weights_path = run_dir / "weights.pt"

    for epoch in range(opts.epochs):
        model.train()
        order = list(range(len(train_data)))
        rng.shuffle(order)
        total_loss, t0 = 0.0, time.perf_counter()
        for step in range(steps_per_epoch):
            idx = order[step * opts.batch_size : (step + 1) * opts.batch_size]
            x, y = train_data.batch(idx, opts.augment, rng)
            xb, yb = torch.from_numpy(x).to(device), torch.from_numpy(y).to(device)
            loss = string_cross_entropy(model(xb), yb, opts.label_smoothing if cfg.name != "baseline" else 0.0)
            optim.zero_grad(set_to_none=True)
            loss.backward()
            optim.step()
            if sched is not None:
                sched.step()
            total_loss += float(loss.detach())
            if on_progress and step % 50 == 0:
                frac = (epoch + step / steps_per_epoch) / opts.epochs
                on_progress(0.15 + 0.85 * frac, f"epoch {epoch + 1}/{opts.epochs} step {step}/{steps_per_epoch}")
        entry: dict[str, object] = {"epoch": epoch + 1, "loss": round(total_loss / steps_per_epoch, 4), "seconds": round(time.perf_counter() - t0, 1)}
        if val_data is not None:
            metrics = evaluate_model(model, val_data, device)
            entry["val"] = metrics.to_dict()
            score = metrics.tab_f1
        else:
            score = -entry["loss"]  # type: ignore[operator]
        history.append(entry)
        (run_dir / "history.json").write_text(json.dumps(history, indent=1))
        if score > best_f1:
            best_f1, best_epoch, bad_epochs = score, epoch + 1, 0
            save_checkpoint(model, cfg, weights_path)
        else:
            bad_epochs += 1
            if val_data is not None and bad_epochs >= opts.patience:
                break

    summary = {
        "run_dir": str(run_dir),
        "weights": str(weights_path),
        "config": cfg.to_dict(),
        "parameters": count_parameters(model),
        "device": device,
        "fold": opts.fold,
        "sources": list(opts.sources),
        "train_excerpts": len(train_ex),
        "val_excerpts": len(val_ex),
        "train_frames": len(train_data),
        "epochs_run": len(history),
        "best_epoch": best_epoch,
        "best_val": next((h["val"] for h in history if h["epoch"] == best_epoch), None),
        "history": history,
    }
    (run_dir / "metrics.json").write_text(json.dumps(summary, indent=1))
    return summary


def save_checkpoint(model, cfg: TabCNNConfig, path: Path) -> None:  # noqa: ANN001
    import torch

    torch.save({"config": cfg.to_dict(), "state_dict": model.state_dict()}, path)


def load_checkpoint(path: Path, device: str = "cpu"):  # noqa: ANN201
    import torch

    ckpt = torch.load(path, map_location=device, weights_only=True)
    cfg = TabCNNConfig(**ckpt["config"])
    model = TabCNN(cfg)
    model.load_state_dict(ckpt["state_dict"])
    return model.to(device), cfg
