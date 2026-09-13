"""End-to-end audio-tier evaluation on GuitarSet: sidecar → quantize → solver → tab vs ground truth.

Runs the real ``guitarista-ml`` sidecar for one held-out player, caches its JSON per excerpt and
model, then scores the *final fretted tab* (not just the transcriber) with the TabCNN paper's
frame-level tab/pitch metrics. Compares ``basic-pitch`` (pitch only → solver picks strings) with
``tabcnn`` (string hints → solver honours them).

    cd apps/api && uv run python scripts/eval_audio_tier.py --fold 5 --models basic-pitch,tabcnn

Needs GuitarSet under apps/ml/data (``guitarista-ml guitarset-fetch``) and, for tabcnn, the
shipped ONNX weights. ``labels``/``metrics`` are imported from apps/ml by path; they are pure numpy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "ml" / "src"))

from guitarista_ml.tabcnn.data import fold_split, list_excerpts  # noqa: E402
from guitarista_ml.tabcnn.features import FPS, N_STRINGS  # noqa: E402
from guitarista_ml.tabcnn.labels import (  # noqa: E402
    canonical_to_model_string,
    frame_labels,
    parse_jams_notes,
)
from guitarista_ml.tabcnn.metrics import compute_metrics  # noqa: E402

from guitarista_api.adapters.ml_sidecar import MLSidecar, TranscribeParams  # noqa: E402
from guitarista_api.domain.transcription import TranscriptionResult  # noqa: E402
from guitarista_api.solver.candidates import CandidateConfig  # noqa: E402
from guitarista_api.solver.cost import CostProfile, cost_for_profile  # noqa: E402
from guitarista_api.solver.instrument import StringConfig  # noqa: E402
from guitarista_api.solver.quantize import estimate_grid, quantize  # noqa: E402
from guitarista_api.solver.search import solve  # noqa: E402


def tab_frames(
    result: TranscriptionResult, n_frames: int, profile: CostProfile, hints: bool
) -> np.ndarray:
    """Quantize + solve the transcription, then paint each source note's final (string, fret)."""
    notes = (
        result.notes
        if hints
        else [n.model_copy(update={"string": None, "fret": None}) for n in result.notes]
    )
    cfg = StringConfig()
    grid = estimate_grid(notes, result.tempo_bpm, beats_s=result.beats_s)
    chords = quantize(notes, grid)
    solved = solve(
        chords,
        cfg,
        cost=cost_for_profile(profile),
        ccfg=CandidateConfig(),
        out_of_range="octave_shift",
    )
    out = np.zeros((n_frames, N_STRINGS), dtype=np.int8)
    for chord, fretting in zip(solved.chords, solved.frettings, strict=True):
        by_pitch = {cfg.pitch_at(n.string, n.fret): n for n in fretting.notes}
        for src in chord.meta.get("source_notes", []):
            fr = by_pitch.get(src.pitch_midi)
            if fr is None:
                continue  # octave-shifted out-of-range pitch; counted as a miss
            lo, hi = int(round(src.onset_s * FPS)), int(round(src.offset_s * FPS))
            out[lo : max(hi, lo + 1), canonical_to_model_string(fr.string)] = fr.fret + 1
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fold", type=int, default=5)
    ap.add_argument("--models", default="basic-pitch,tabcnn")
    ap.add_argument("--source", default="mic")
    ap.add_argument("--profile", default="tabgen")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ml-cmd", default=f"uv run --directory {ROOT / 'apps' / 'ml'} guitarista-ml")
    ap.add_argument(
        "--cache", type=Path, default=ROOT / "apps" / "ml" / "data" / "cache" / "sidecar"
    )
    args = ap.parse_args()

    _, excerpts = fold_split(list_excerpts(sources=(args.source,)), args.fold)
    if args.limit:
        excerpts = excerpts[: args.limit]
    sidecar = MLSidecar(args.ml_cmd)
    args.cache.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "fold": args.fold,
        "source": args.source,
        "excerpts": len(excerpts),
        "profile": args.profile,
    }

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        preds_h, preds_nh, gts = [], [], []
        for i, ex in enumerate(excerpts):
            cached = args.cache / f"{ex.id}__{args.source}__{model}.json"
            if cached.exists():
                result = TranscriptionResult.model_validate_json(cached.read_text())
            else:
                result = await sidecar.transcribe(
                    ex.audio[args.source],
                    args.cache / "tmp.json",
                    TranscribeParams(model=model, estimate_tempo=True),
                )
                cached.write_text(result.model_dump_json())
            duration = max([n.offset_s for n in result.notes] + [0.0])
            n_frames = int(np.ceil(duration * FPS)) + 1
            gt_notes = parse_jams_notes(ex.jams)
            gt_end = max(n.onset_s + n.duration_s for n in gt_notes)
            n_frames = max(n_frames, int(np.ceil(gt_end * FPS)) + 1)
            gt = frame_labels(gt_notes, n_frames)
            preds_h.append(tab_frames(result, n_frames, args.profile, hints=True))
            preds_nh.append(tab_frames(result, n_frames, args.profile, hints=False))
            gts.append(gt)
            print(
                f"[{model}] {i + 1}/{len(excerpts)} {ex.id}: {len(result.notes)} notes",
                file=sys.stderr,
            )
        gt_all = np.concatenate(gts)
        entry = {"solver_only": compute_metrics(np.concatenate(preds_nh), gt_all).to_dict()}
        if model == "tabcnn":
            entry["with_hints"] = compute_metrics(np.concatenate(preds_h), gt_all).to_dict()
        report[model] = entry
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
