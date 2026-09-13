"""Convert notation formats music21 cannot read by shelling out to MuseScore Studio.

MuseScore Studio is free (GPL) and imports far more than MusicXML -- ``.mscz``/``.mscx``, Guitar
Pro, Capella -- so one ``mscore -o out.musicxml in.mscz`` call widens score import a long way.
It is an *optional* dependency: when the binary is absent, callers fall back to the music21-native
formats and say so.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

INSTALL_HINT = (
    "install MuseScore Studio (free, https://musescore.org/download) or set GUITARISTA_MSCORE_BIN; "
    "alternatively export MusicXML from MuseScore yourself and upload that"
)

#: Probed in order when the configured binary is not on PATH. MuseScore ships as a macOS .app
#: bundle and under several names on Linux, none of which is reliably called ``mscore``.
FALLBACK_BINARIES = (
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    "mscore",
    "musescore",
    "mscore4portable",
    "MuseScore-4",
    "mscore3",
)


class MuseScoreError(Exception):
    pass


class MuseScoreMissing(MuseScoreError):
    def __init__(self) -> None:
        super().__init__(f"MuseScore not found; {INSTALL_HINT}")


#: ``settings.mscore_bin`` default. Anything else counts as an explicit choice by the operator.
DEFAULT_BIN = "mscore"


def _executable(candidate: str) -> str | None:
    found = shutil.which(candidate)
    if found is not None:
        return found
    # shutil.which only reports absolute paths that are executable; macOS .app bundle paths are
    # not on PATH, so check them directly too.
    path = Path(candidate)
    return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None


@lru_cache(maxsize=8)
def resolve_mscore(bin_hint: str = DEFAULT_BIN) -> str | None:
    """Absolute path to a usable MuseScore binary, or ``None`` when it is not installed.

    An explicit ``bin_hint`` (anything but the default) is authoritative: we do *not* fall back to
    the well-known locations, so pointing ``GUITARISTA_MSCORE_BIN`` at a nonexistent path is a
    supported way to turn the MuseScore formats off on a machine that happens to have it installed.
    """
    if bin_hint and bin_hint != DEFAULT_BIN:
        return _executable(bin_hint)
    return next((found for c in FALLBACK_BINARIES if (found := _executable(c))), None)


def musescore_available(bin_hint: str = DEFAULT_BIN) -> bool:
    return resolve_mscore(bin_hint) is not None


async def to_musicxml(
    src: Path, dst: Path, *, mscore_bin: str = DEFAULT_BIN, timeout_s: float = 60.0
) -> Path:
    """Convert any MuseScore-readable score at ``src`` to uncompressed MusicXML at ``dst``."""
    mscore = resolve_mscore(mscore_bin)
    if mscore is None:
        raise MuseScoreMissing()
    await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
    argv = [mscore, "-o", str(dst), str(src)]
    rc, err = await _run(argv, env=_env(), timeout_s=timeout_s)
    exists = await asyncio.to_thread(dst.exists)
    # mscore exits 0 while writing nothing for some unreadable inputs, so the output is the real
    # success signal. Its stderr is full of Qt/QML warnings even on success -- never a signal.
    if rc != 0 or not exists or await asyncio.to_thread(lambda: dst.stat().st_size) == 0:
        await asyncio.to_thread(dst.unlink, missing_ok=True)
        detail = _clean_stderr(err) or f"exit code {rc}"
        raise MuseScoreError(f"MuseScore could not convert {src.name}: {detail}")
    return dst


def _env() -> dict[str, str]:
    """MuseScore is a GUI app and will not start on a headless Linux box without an offscreen
    Qt platform. macOS must NOT get this -- it only ships the ``cocoa`` plugin and setting
    ``offscreen`` there makes MuseScore fail to start outright."""
    env = {**os.environ}
    if sys.platform.startswith("linux"):
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


async def _run(argv: list[str], *, env: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise MuseScoreMissing() from exc
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError as exc:
        _kill(proc)
        await proc.wait()
        raise MuseScoreError(f"MuseScore timed out after {timeout_s:g}s") from exc
    except asyncio.CancelledError:
        _kill(proc)
        await proc.wait()
        raise
    return proc.returncode or 0, err


def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()


#: Qt chatters on stderr on every run; keeping it would bury the real message.
_NOISE_PREFIXES = ("qt.", "QML", "Qt ", "qml:")


def _clean_stderr(raw: bytes) -> str:
    lines = [
        line.strip()
        for line in raw.decode("utf-8", "replace").splitlines()
        if line.strip() and not line.strip().startswith(_NOISE_PREFIXES)
    ]
    return " / ".join(lines[-3:])[:400]
