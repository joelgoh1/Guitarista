"""stdout/stderr plumbing for the JSON-lines contract."""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Iterator
from typing import Any


class CliError(Exception):
    """An error that maps to a JSON error object and a process exit code."""

    def __init__(self, message: str, *, type: str = "error", exit_code: int = 1) -> None:
        super().__init__(message)
        self.type = type
        self.exit_code = exit_code


def emit_result(obj: Any) -> None:
    """Print the single JSON result object on stdout (always the last line)."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_progress(progress: float, stage: str) -> None:
    sys.stderr.write(json.dumps({"progress": round(max(0.0, min(1.0, progress)), 4), "stage": stage}) + "\n")
    sys.stderr.flush()


@contextlib.contextmanager
def quiet_stdout() -> Iterator[None]:
    """Route library chatter (basic-pitch ``print``s, torch hub logs) to stderr.

    stdout is reserved for the final JSON object.
    """
    with contextlib.redirect_stdout(sys.stderr):
        yield
