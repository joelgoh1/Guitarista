"""Subprocess driver for the ``guitarista-ml`` sidecar (``apps/ml``).

Contract (see ``apps/ml/README.md``): every command prints one JSON object as the last stdout
line; progress goes to stderr as ``{"progress": 0..1, "stage": "..."}`` lines (mixed with library
chatter, which is ignored); failures exit non-zero with ``{"error", "type"}``; exit 3 means Demucs
is not installed.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import shlex
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from guitarista_api.domain.transcription import TranscriptionResult
from guitarista_api.settings import Settings

log = structlog.get_logger(__name__)

ProgressCallback = Callable[[float, str], Awaitable[None] | None]

EXIT_NOT_FOUND = 127
EXIT_DEMUCS_MISSING = 3
TERMINATE_GRACE_S = 5.0
SETUP_HINT = "run `uv sync` in apps/ml (and `uv sync --extra separate` for Demucs)"


class SidecarError(Exception):
    """The sidecar exited non-zero or could not be started."""

    def __init__(self, exit_code: int, message: str, type: str = "unknown") -> None:
        super().__init__(f"[{type}] {message} (exit {exit_code})")
        self.exit_code = exit_code
        self.message = message
        self.type = type

    @property
    def demucs_missing(self) -> bool:
        return self.exit_code == EXIT_DEMUCS_MISSING


@dataclass(frozen=True, slots=True)
class SidecarCapabilities:
    basic_pitch: bool
    backend: str | None
    demucs: bool
    device: str
    torch: str | None
    tabcnn: bool = False

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SidecarCapabilities:
        return cls(
            basic_pitch=bool(data.get("basic_pitch", False)),
            backend=data.get("backend"),
            demucs=bool(data.get("demucs", False)),
            tabcnn=bool(data.get("tabcnn", False)),
            device=str(data.get("device") or "cpu"),
            torch=data.get("torch"),
        )


@dataclass(frozen=True, slots=True)
class TranscribeParams:
    onset: float | None = None
    frame: float | None = None
    min_note_ms: float | None = None
    fmin: float | None = 80.0
    fmax: float | None = 1300.0
    estimate_tempo: bool = True
    model: str = "basic-pitch"

    def to_args(self) -> list[str]:
        args: list[str] = ["--model", self.model]
        for flag, value in (
            ("--onset", self.onset),
            ("--frame", self.frame),
            ("--min-note-ms", self.min_note_ms),
            ("--fmin", self.fmin),
            ("--fmax", self.fmax),
        ):
            if value is not None:
                args += [flag, str(value)]
        if self.estimate_tempo:
            args.append("--estimate-tempo")
        return args


class MLSidecar:
    """Async wrapper around the sidecar CLI. One instance per process; ``probe()`` is cached."""

    def __init__(
        self,
        cmd: str | Sequence[str],
        env: Mapping[str, str] | None = None,
        models_dir: Path | None = None,
    ) -> None:
        self.cmd: list[str] = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        if not self.cmd:
            raise ValueError("ml sidecar command must not be empty")
        self.env = dict(env or {})
        self.models_dir = models_dir
        if models_dir is not None:
            self.env.setdefault("TORCH_HOME", str(Path(models_dir).resolve() / "torch"))
        self._probed = False
        self._caps: SidecarCapabilities | None = None
        self._probe_error: str | None = None
        self._probe_lock = asyncio.Lock()
        self._probe_task: asyncio.Task[SidecarCapabilities | None] | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> MLSidecar:
        return cls(settings.ml_cmd, models_dir=settings.ml_models_dir)

    # ------------------------------------------------------------------ probe

    @property
    def probed(self) -> bool:
        return self._probed

    @property
    def capabilities(self) -> SidecarCapabilities | None:
        """Cached probe result (``None`` when not probed yet or the probe failed)."""
        return self._caps

    @property
    def probe_error(self) -> str | None:
        return self._probe_error

    async def probe(self, *, force: bool = False) -> SidecarCapabilities | None:
        """Run ``probe`` once per process; returns ``None`` if the sidecar cannot be started."""
        async with self._probe_lock:
            if self._probed and not force:
                return self._caps
            try:
                data = await self._run(["probe"])
                self._caps = SidecarCapabilities.from_json(data)
                self._probe_error = None
            except SidecarError as exc:
                self._caps = None
                self._probe_error = exc.message
                log.warning("ml_sidecar.probe_failed", cmd=self.cmd, error=exc.message)
            self._probed = True
            return self._caps

    def start_probe(self) -> asyncio.Task[SidecarCapabilities | None]:
        """Kick off the probe in the background (idempotent); result lands in ``capabilities``."""
        if self._probe_task is None or (self._probe_task.done() and not self._probed):
            self._probe_task = asyncio.create_task(self.probe(), name="ml-sidecar-probe")
        return self._probe_task

    async def close(self) -> None:
        if self._probe_task is not None and not self._probe_task.done():
            self._probe_task.cancel()
            await asyncio.gather(self._probe_task, return_exceptions=True)

    # --------------------------------------------------------------- commands

    async def version(self) -> str:
        data = await self._run(["version"])
        return str(data.get("version", ""))

    async def transcribe(
        self,
        wav: Path,
        out_json: Path,
        params: TranscribeParams | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        params = params or TranscribeParams()
        await asyncio.to_thread(out_json.parent.mkdir, parents=True, exist_ok=True)
        await self._run(
            ["transcribe", str(wav), str(out_json), *params.to_args()], on_progress=on_progress
        )
        try:
            raw = json.loads(await asyncio.to_thread(out_json.read_text))
        except (OSError, ValueError) as exc:
            msg = f"sidecar wrote no readable result to {out_json}"
            raise SidecarError(0, msg, "output") from exc
        return parse_transcription(raw)

    async def separate(
        self,
        wav: Path,
        out_dir: Path,
        model: str = "htdemucs_6s",
        stems: Sequence[str] = ("guitar", "other"),
        on_progress: ProgressCallback | None = None,
        device: str = "auto",
    ) -> dict[str, Path]:
        await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)
        args = ["separate", str(wav), str(out_dir), "--model", model, "--device", device]
        if stems:
            args += ["--stems", ",".join(stems)]
        data = await self._run(args, on_progress=on_progress)
        raw = data.get("stems")
        if not isinstance(raw, dict):
            raise SidecarError(0, "separate result has no 'stems' mapping", "output")
        return {str(name): Path(str(path)) for name, path in raw.items()}

    # ------------------------------------------------------------------ core

    async def _run(
        self, args: Sequence[str], on_progress: ProgressCallback | None = None
    ) -> dict[str, Any]:
        argv = [*self.cmd, *args]
        env = {**os.environ, **self.env}
        log.debug("ml_sidecar.spawn", argv=argv)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except (FileNotFoundError, PermissionError) as exc:
            msg = f"ML sidecar command not found: {argv[0]!r}; {SETUP_HINT}"
            raise SidecarError(EXIT_NOT_FOUND, msg, "not_found") from exc
        assert proc.stdout is not None and proc.stderr is not None
        stderr_tail: list[str] = []
        try:
            stdout_bytes, _ = await asyncio.gather(
                proc.stdout.read(), self._pump_stderr(proc.stderr, stderr_tail, on_progress)
            )
            rc = await proc.wait()
        except asyncio.CancelledError:
            await _terminate(proc)
            raise
        return _parse_result(argv, rc, stdout_bytes.decode("utf-8", "replace"), stderr_tail)

    @staticmethod
    async def _pump_stderr(
        stream: asyncio.StreamReader, tail: list[str], on_progress: ProgressCallback | None
    ) -> None:
        while True:
            raw = await stream.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip()
            progress = _parse_progress(line)
            if progress is None:
                if line:
                    tail.append(line)
                    del tail[:-20]
                continue
            if on_progress is not None:
                result = on_progress(*progress)
                if inspect.isawaitable(result):
                    await result


def _parse_progress(line: str) -> tuple[float, str] | None:
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict) or "progress" not in data:
        return None
    try:
        value = float(data["progress"])
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value)), str(data.get("stage", ""))


def _parse_result(
    argv: Sequence[str], rc: int, stdout: str, stderr_tail: Sequence[str]
) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            break
        if isinstance(obj, dict):
            payload = obj
        break
    if rc != 0:
        if payload is not None and "error" in payload:
            raise SidecarError(rc, str(payload["error"]), str(payload.get("type", "unknown")))
        tail = " | ".join(stderr_tail[-3:]) or "no output"
        raise SidecarError(rc, f"{argv[0]} exited with {rc}: {tail}", "crash")
    if payload is None:
        raise SidecarError(0, "sidecar printed no JSON result", "output")
    return payload


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_S)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()


def parse_transcription(raw: Mapping[str, Any]) -> TranscriptionResult:
    """Normalize the sidecar's ``TranscriptionResult`` JSON into the API domain model.

    Extra keys (``pitch_bend``, ``source_audio``, ``stem``) are ignored, ``null`` velocity or
    confidence is dropped so defaults apply, and out-of-range values are clamped.
    """
    notes: list[dict[str, Any]] = []
    for n in raw.get("notes", []) or []:
        note = {
            "pitch_midi": int(n["pitch_midi"]),
            "onset_s": max(0.0, float(n["onset_s"])),
            "offset_s": max(0.0, float(n["offset_s"])),
        }
        for key in ("velocity", "confidence"):
            value = n.get(key)
            if value is not None:
                note[key] = max(0.0, min(1.0, float(value)))
        if n.get("string") is not None and n.get("fret") is not None:
            note["string"], note["fret"] = int(n["string"]), int(n["fret"])
        notes.append(note)
    beats = [float(b) for b in raw.get("beats_s") or [] if b is not None and float(b) >= 0]
    result = TranscriptionResult(
        notes=notes,  # type: ignore[arg-type]
        tempo_bpm=raw.get("tempo_bpm"),
        beats_s=sorted(beats),
        duration_s=raw.get("duration_s"),
        model=raw.get("model"),
        warnings=list(raw.get("warnings", []) or []),
    )
    return result
