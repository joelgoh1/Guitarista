"""Stand-in for the ``guitarista-ml`` CLI used by the API test-suite (stdlib only).

Speaks the same contract: last stdout line is JSON, progress lines on stderr, ``{"error","type"}``
with a non-zero exit on failure. ``separate`` always exits 3 (Demucs not installed).

Knobs (environment): ``FAKE_ML_FAIL=1`` makes ``transcribe`` exit 4 with a model error;
``FAKE_ML_SLEEP=<seconds>`` makes ``transcribe`` sleep before finishing (cancellation tests);
``FAKE_ML_PROBE_DEMUCS=1`` reports Demucs as available; ``FAKE_ML_TABCNN=1`` reports TabCNN and,
when ``--model tabcnn`` is passed, attaches string/fret hints to the fixture notes.
"""

from __future__ import annotations

import json
import os
import sys
import time

FIXTURE_NOTES = [  # E2 A2 D3, one per second
    {
        "onset_s": float(i),
        "offset_s": i + 0.9,
        "pitch_midi": p,
        "velocity": v,
        "pitch_bend": None,
        "confidence": v,
    }
    for i, (p, v) in enumerate([(40, 0.8), (45, 0.7), (50, 0.9)])
]


def emit(obj: object) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def progress(value: float, stage: str) -> None:
    sys.stderr.write(json.dumps({"progress": value, "stage": stage}) + "\n")
    sys.stderr.flush()


def fail(message: str, type_: str, code: int) -> int:
    emit({"error": message, "type": type_})
    return code


def main(argv: list[str]) -> int:
    if not argv:
        return fail("no command", "usage", 2)
    cmd, args = argv[0], argv[1:]
    if cmd == "version":
        emit({"version": "0.0.0-fake"})
        return 0
    if cmd == "probe":
        emit(
            {
                "basic_pitch": True,
                "backend": "fake",
                "demucs": os.environ.get("FAKE_ML_PROBE_DEMUCS") == "1",
                "tabcnn": os.environ.get("FAKE_ML_TABCNN") == "1",
                "device": "cpu",
                "torch": None,
            }
        )
        return 0
    if cmd == "transcribe":
        if len(args) < 2:
            return fail("usage: transcribe IN.wav OUT.json", "usage", 2)
        src, out = args[0], args[1]
        if not os.path.exists(src):
            return fail(f"input not found: {src}", "invalid_input", 2)
        if not src.lower().endswith(".wav"):
            return fail("only .wav input is accepted", "invalid_input", 2)
        sys.stderr.write("UserWarning: pkg_resources is deprecated (library chatter)\n")
        progress(0.0, "load")
        if os.environ.get("FAKE_ML_FAIL") == "1":
            return fail("model inference exploded", "inference", 4)
        sleep = float(os.environ.get("FAKE_ML_SLEEP", "0") or 0)
        if sleep:
            time.sleep(sleep)
        progress(0.5, "infer")
        estimate_tempo = "--estimate-tempo" in args
        model = args[args.index("--model") + 1] if "--model" in args else "basic-pitch"
        notes = [dict(n) for n in FIXTURE_NOTES]
        if model == "tabcnn":
            if os.environ.get("FAKE_ML_TABCNN") != "1":
                return fail("TabCNN weights are not installed", "model_load", 4)
            # Deliberately un-tabgen-like: A2 and D3 fretted at fret 5 instead of open strings.
            for n, hint in zip(notes, [(6, 0), (6, 5), (5, 5)], strict=True):
                n["string"], n["fret"] = hint
        result = {
            "notes": notes,
            "tempo_bpm": 60.0 if estimate_tempo else None,
            "beats_s": [0.0, 1.0, 2.0] if estimate_tempo else [],
            "source_audio": os.path.abspath(src),
            "stem": "mix",
            "model": f"fake/{model}",
            "duration_s": 3.0,
        }
        with open(out, "w") as fh:
            json.dump(result, fh)
        progress(1.0, "done")
        emit(
            {
                "ok": True,
                "out": out,
                "note_count": len(notes),
                "tempo_bpm": result["tempo_bpm"],
            }
        )  # noqa: E501
        return 0
    if cmd == "separate":
        return fail(
            "demucs is not installed; run `uv sync --extra separate`", "missing_dependency", 3
        )  # noqa: E501
    return fail(f"unknown command {cmd!r}", "usage", 2)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
