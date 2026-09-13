"""``guitarista-ml`` entry point.

Contract: the final line on stdout is one JSON object. Progress is written to
stderr as ``{"progress": 0..1, "stage": "..."}`` lines. On failure the process
exits non-zero and stdout carries ``{"error": "...", "type": "..."}``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from guitarista_ml import __version__
from guitarista_ml.io import CliError, emit_result
from guitarista_ml.schema import SeparateOptions, TranscribeOptions


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="guitarista-ml", description="Guitarista ML sidecar (JSON over stdout)")
    p.add_argument("-v", "--verbose", action="store_true", help="log at INFO level on stderr")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the sidecar version")
    sub.add_parser("probe", help="report available backends/devices without crashing")

    t = sub.add_parser("transcribe", help="transcribe a wav to note events with basic-pitch")
    t.add_argument("input", type=Path, metavar="IN.wav")
    t.add_argument("output", type=Path, metavar="OUT.json")
    t.add_argument("--onset", type=float, default=0.5, help="onset threshold (default 0.5)")
    t.add_argument("--frame", type=float, default=0.3, help="frame threshold (default 0.3)")
    t.add_argument("--min-note-ms", type=float, default=58.0, help="minimum note length in ms (default 58)")
    t.add_argument("--fmin", type=float, default=80.0, help="minimum frequency in Hz (default 80)")
    t.add_argument("--fmax", type=float, default=1300.0, help="maximum frequency in Hz (default 1300)")
    t.add_argument("--estimate-tempo", action="store_true", help="also estimate tempo with librosa")
    t.add_argument(
        "--model",
        choices=["basic-pitch", "tabcnn"],
        default="basic-pitch",
        help="basic-pitch (pitch only, default) or tabcnn (string/fret; needs shipped ONNX weights)",
    )

    s = sub.add_parser("separate", help="separate a wav into stems with Demucs (extra: separate)")
    s.add_argument("input", type=Path, metavar="IN.wav")
    s.add_argument("output_dir", type=Path, metavar="OUT_DIR")
    s.add_argument("--model", default="htdemucs_6s", help="demucs model name (default htdemucs_6s)")
    s.add_argument("--stems", default="guitar,other", help="comma-separated stems to save (default guitar,other)")
    s.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")

    g = sub.add_parser("guitarset-fetch", help="download GuitarSet (CC-BY-4.0) into $GUITARISTA_ML_DATA")
    g.add_argument("--parts", default="annotation,mic", help="comma list of annotation,mic,mix (default annotation,mic)")

    tr = sub.add_parser("tabcnn-train", help="train TabCNN on GuitarSet (extra: train)")
    tr.add_argument("--config", choices=["baseline", "improved"], default="improved")
    tr.add_argument("--fold", default="5", help="held-out player 0-5, or 'all' to train on everyone (default 5)")
    tr.add_argument("--sources", default="mic", help="comma list of mic,mix audio sources (default mic)")
    tr.add_argument("--epochs", type=int, default=30)
    tr.add_argument("--batch-size", type=int, default=256)
    tr.add_argument("--lr", type=float, default=1e-3)
    tr.add_argument("--patience", type=int, default=5)
    tr.add_argument("--no-augment", action="store_true")
    tr.add_argument("--limit", type=int, default=None, help="debug: only use this many excerpts")
    tr.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    tr.add_argument("--out", type=Path, default=Path("runs"))

    ex = sub.add_parser("tabcnn-export", help="export a training checkpoint to ONNX (extra: train)")
    ex.add_argument("weights", type=Path, metavar="WEIGHTS.pt")
    ex.add_argument("output", type=Path, nargs="?", default=None, metavar="OUT.onnx (default: shipped path)")

    ev = sub.add_parser("tabcnn-eval", help="score tabcnn and/or basic-pitch on a held-out GuitarSet player")
    ev.add_argument("--fold", type=int, default=5)
    ev.add_argument("--model", choices=["tabcnn", "basic-pitch", "both"], default="tabcnn")
    ev.add_argument("--weights", type=Path, default=None)
    ev.add_argument("--source", choices=["mic", "mix"], default="mic")
    ev.add_argument("--switch-penalty", type=float, default=2.0)
    ev.add_argument("--limit", type=int, default=None)
    return p


def _run(args: argparse.Namespace) -> object:
    if args.command == "version":
        return {"version": __version__}
    if args.command == "probe":
        from guitarista_ml.probe import probe

        return probe()
    if args.command == "transcribe":
        from guitarista_ml.transcribe import transcribe_to_file

        opts = TranscribeOptions(
            onset_threshold=args.onset,
            frame_threshold=args.frame,
            min_note_ms=args.min_note_ms,
            fmin=args.fmin,
            fmax=args.fmax,
            estimate_tempo=args.estimate_tempo,
            model=args.model,
        )
        return transcribe_to_file(args.input, args.output, opts)
    if args.command == "guitarset-fetch":
        return _guitarset_fetch(args)
    if args.command == "tabcnn-train":
        return _tabcnn_train(args)
    if args.command == "tabcnn-export":
        return _tabcnn_export(args)
    if args.command == "tabcnn-eval":
        return _tabcnn_eval(args)
    if args.command == "separate":
        from guitarista_ml.separate import separate

        stems = [s.strip() for s in args.stems.split(",") if s.strip()]
        opts = SeparateOptions(model=args.model, stems=stems, device=args.device)
        return separate(args.input, args.output_dir, opts)
    raise CliError(f"unknown command {args.command!r}", type="usage", exit_code=2)


def _require_train_extra() -> None:
    import importlib.util

    if importlib.util.find_spec("torch") is None:
        raise CliError(
            "torch is not installed; run `uv sync --extra train` in apps/ml", type="missing_dependency", exit_code=3
        )


def _guitarset_fetch(args: argparse.Namespace) -> object:
    from guitarista_ml.io import emit_progress
    from guitarista_ml.tabcnn.data import fetch_guitarset, list_excerpts

    parts = [p.strip() for p in args.parts.split(",") if p.strip()]
    root = fetch_guitarset(parts, on_progress=lambda part, frac: emit_progress(frac, f"download {part}"))
    audio = [p for p in parts if p != "annotation"] or ["mic"]
    try:
        n = len(list_excerpts(sources=tuple(audio)))
    except FileNotFoundError:
        n = 0
    return {"root": str(root), "parts": parts, "excerpts": n}


def _tabcnn_train(args: argparse.Namespace) -> object:
    _require_train_extra()
    from guitarista_ml.io import emit_progress
    from guitarista_ml.tabcnn.train import TrainOptions, train

    opts = TrainOptions(
        config=args.config,
        fold=None if args.fold == "all" else int(args.fold),
        sources=tuple(s.strip() for s in args.sources.split(",") if s.strip()),
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        augment=not args.no_augment,
        limit_excerpts=args.limit,
        device=args.device,
        out_dir=args.out,
    )
    summary = train(opts, on_progress=emit_progress)
    summary.pop("history", None)
    return summary


def _tabcnn_export(args: argparse.Namespace) -> object:
    _require_train_extra()
    from guitarista_ml.tabcnn.export import export_onnx
    from guitarista_ml.tabcnn.infer import DEFAULT_WEIGHTS

    return export_onnx(args.weights, args.output or DEFAULT_WEIGHTS)


def _tabcnn_eval(args: argparse.Namespace) -> object:
    from guitarista_ml.io import emit_progress
    from guitarista_ml.tabcnn.evaluate import evaluate_basic_pitch, evaluate_tabcnn, held_out
    from guitarista_ml.tabcnn.infer import DEFAULT_WEIGHTS

    excerpts = held_out(args.fold, args.source, args.limit)
    out: dict[str, object] = {"fold": args.fold, "source": args.source, "excerpts": len(excerpts)}
    if args.model in ("tabcnn", "both"):
        res = evaluate_tabcnn(
            excerpts,
            args.weights or DEFAULT_WEIGHTS,
            args.source,
            args.switch_penalty,
            on_progress=lambda i, n: emit_progress(0.5 * i / n, f"tabcnn {i}/{n}"),
        )
        res.pop("per_excerpt", None)
        out["tabcnn"] = res
    if args.model in ("basic-pitch", "both"):
        out["basic_pitch"] = evaluate_basic_pitch(
            excerpts, args.source, on_progress=lambda i, n: emit_progress(0.5 + 0.5 * i / n, f"basic-pitch {i}/{n}")
        )
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO if args.verbose else logging.WARNING)
    try:
        emit_result(_run(args))
        return 0
    except CliError as exc:
        emit_result({"error": str(exc), "type": exc.type})
        return exc.exit_code
    except KeyboardInterrupt:
        emit_result({"error": "interrupted", "type": "interrupted"})
        return 130
    except Exception as exc:  # last resort: never leave stdout without JSON
        logging.exception("unhandled error")
        emit_result({"error": f"{exc!r}", "type": exc.__class__.__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
