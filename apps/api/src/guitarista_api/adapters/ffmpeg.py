"""Thin async wrappers around ``ffmpeg`` / ``ffprobe`` for the audio tier."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

INSTALL_HINT = "install ffmpeg (e.g. `brew install ffmpeg`) or set GUITARISTA_FFMPEG_BIN"


class FfmpegError(Exception):
    pass


class FfmpegMissing(FfmpegError):
    def __init__(self, binary: str) -> None:
        super().__init__(f"{binary!r} not found on PATH; {INSTALL_HINT}")
        self.binary = binary


@dataclass(frozen=True, slots=True)
class AudioInfo:
    duration_s: float | None
    sample_rate: int | None
    channels: int | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }


def ffmpeg_available(ffmpeg_bin: str = "ffmpeg") -> bool:
    return shutil.which(ffmpeg_bin) is not None


def ffprobe_bin_for(ffmpeg_bin: str = "ffmpeg") -> str:
    """``ffprobe`` living next to the configured ``ffmpeg`` (same directory / suffix)."""
    p = Path(ffmpeg_bin)
    name = p.name.replace("ffmpeg", "ffprobe") if "ffmpeg" in p.name else "ffprobe"
    return str(p.with_name(name)) if p.parent != Path() else name


def _resolve(binary: str) -> str:
    found = shutil.which(binary)
    if found is None:
        raise FfmpegMissing(binary)
    return found


async def _run(argv: list[str], *, binary: str) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise FfmpegMissing(binary) from exc
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    return proc.returncode or 0, out, err


async def probe_audio(path: Path, ffmpeg_bin: str = "ffmpeg") -> AudioInfo:
    """Duration / sample rate / channels via ``ffprobe -show_format -show_streams``."""
    probe = _resolve(ffprobe_bin_for(ffmpeg_bin))
    argv = [
        probe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-select_streams",
        "a:0",
        str(path),
    ]
    rc, out, err = await _run(argv, binary=probe)
    if rc != 0:
        raise FfmpegError(f"ffprobe failed on {path.name}: {_text(err)}")
    try:
        data = json.loads(out.decode("utf-8", "replace") or "{}")
    except ValueError as exc:
        raise FfmpegError("ffprobe returned invalid JSON") from exc
    streams = data.get("streams") or []
    if not streams:
        raise FfmpegError(f"{path.name} has no audio stream")
    stream = streams[0]
    fmt = data.get("format") or {}
    duration = _to_float(fmt.get("duration")) or _to_float(stream.get("duration"))
    sr = _to_int(stream.get("sample_rate"))
    return AudioInfo(duration_s=duration, sample_rate=sr, channels=_to_int(stream.get("channels")))


async def to_wav_mono(src: Path, dst: Path, sr: int = 22050, ffmpeg_bin: str = "ffmpeg") -> Path:
    """Decode anything ffmpeg understands to a mono 16-bit PCM wav at ``sr`` Hz."""
    ffmpeg = _resolve(ffmpeg_bin)
    await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
    argv = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(dst),
    ]
    rc, _, err = await _run(argv, binary=ffmpeg)
    if rc != 0 or not await asyncio.to_thread(dst.exists):
        raise FfmpegError(f"ffmpeg failed to convert {src.name}: {_text(err)[-400:]}")
    return dst


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").strip()


def _to_float(value: object) -> float | None:
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_int(value: object) -> int | None:
    if isinstance(value, int | float | str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None
