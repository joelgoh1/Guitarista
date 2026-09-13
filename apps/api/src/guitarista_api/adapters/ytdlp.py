"""Fetch a song's audio with ``yt-dlp`` (``ytsearch1:"artist title"`` or a direct URL).

``search_candidates`` lists several search hits (metadata only, no download) so callers can pick
the right recording before spending a download on it; see ``services/yt_match.py``.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

INSTALL_HINT = "install yt-dlp (e.g. `brew install yt-dlp`) or set GUITARISTA_YTDLP_BIN"
WATCH_URL = "https://www.youtube.com/watch?v={id}"
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class YtdlpError(Exception):
    pass


class YtdlpMissing(YtdlpError):
    def __init__(self, binary: str) -> None:
        super().__init__(f"{binary!r} not found on PATH; {INSTALL_HINT}")
        self.binary = binary


@dataclass(frozen=True, slots=True)
class YtCandidate:
    """One search hit, from ``--flat-playlist --dump-json`` (no download yet)."""

    video_id: str
    url: str
    title: str
    uploader: str
    duration_s: float | None
    is_live: bool = False


def ytdlp_available(ytdlp_bin: str = "yt-dlp") -> bool:
    return shutil.which(ytdlp_bin) is not None


def search_target(query_or_url: str) -> str:
    query_or_url = query_or_url.strip()
    if _URL_RE.match(query_or_url):
        return query_or_url
    return f'ytsearch1:"{query_or_url}"'


def _resolve_binary(ytdlp_bin: str) -> str:
    binary = shutil.which(ytdlp_bin)
    if binary is None:
        raise YtdlpMissing(ytdlp_bin)
    return binary


async def _run(argv: list[str], ytdlp_bin: str, timeout_s: float) -> tuple[str, str]:
    """Run yt-dlp, returning decoded ``(stdout, stderr)``; non-zero exit raises ``YtdlpError``."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise YtdlpMissing(ytdlp_bin) from exc
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
    except (asyncio.CancelledError, TimeoutError):
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    stderr = err.decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise YtdlpError(f"yt-dlp failed ({proc.returncode}): {stderr[-400:] or 'no output'}")
    return out.decode("utf-8", "replace"), stderr


async def search_candidates(
    query: str,
    *,
    limit: int = 5,
    ytdlp_bin: str = "yt-dlp",
    timeout_s: float = 60.0,
) -> list[YtCandidate]:
    """Return up to ``limit`` search hits for ``query`` without downloading anything.

    Malformed or entry-less JSON lines are skipped rather than failing the whole search.
    """
    query = query.strip()
    if not query:
        return []
    binary = _resolve_binary(ytdlp_bin)
    argv = [
        binary,
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--no-progress",
        f"ytsearch{max(1, int(limit))}:{query}",
    ]
    out, _ = await _run(argv, ytdlp_bin, timeout_s)
    candidates: list[YtCandidate] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        parsed = _parse_entry(entry)
        if parsed is not None:
            candidates.append(parsed)
    return candidates


def _parse_entry(entry: dict[str, object]) -> YtCandidate | None:
    video_id = entry.get("id")
    if not isinstance(video_id, str) or not video_id:
        return None
    title = entry.get("title")
    uploader = entry.get("uploader") or entry.get("channel") or entry.get("uploader_id") or ""
    url = entry.get("url")
    duration = entry.get("duration")
    return YtCandidate(
        video_id=video_id,
        url=url if isinstance(url, str) and _URL_RE.match(url) else WATCH_URL.format(id=video_id),
        title=title if isinstance(title, str) else "",
        uploader=uploader if isinstance(uploader, str) else "",
        duration_s=float(duration) if isinstance(duration, (int, float)) else None,
        is_live=bool(entry.get("is_live") or entry.get("live_status") == "is_live"),
    )


async def fetch_audio(
    query_or_url: str,
    out_dir: Path,
    max_duration_s: int = 600,
    *,
    ytdlp_bin: str = "yt-dlp",
    ffmpeg_bin: str | None = None,
    timeout_s: float = 300.0,
) -> Path:
    """Download the best audio for ``query_or_url`` as wav into ``out_dir`` and return its path.

    Videos longer than ``max_duration_s`` are rejected via ``--match-filter``.
    """
    binary = _resolve_binary(ytdlp_bin)
    await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)
    argv = [
        binary,
        "-x",
        "--audio-format",
        "wav",
        "--no-playlist",
        "--no-progress",
        "--no-warnings",
        "--match-filter",
        f"duration<={int(max_duration_s)}",
        "--print",
        "after_move:filepath",
        "-o",
        str(out_dir / "ytdlp.%(ext)s"),
    ]
    if ffmpeg_bin:
        located = shutil.which(ffmpeg_bin)
        if located:
            argv += ["--ffmpeg-location", str(Path(located).parent)]
    argv.append(search_target(query_or_url))
    out, stderr = await _run(argv, ytdlp_bin, timeout_s)
    printed = [line.strip() for line in out.splitlines() if line.strip()]
    candidates = [Path(p) for p in printed if p.lower().endswith(".wav")]
    candidates = await asyncio.to_thread(_existing_or_glob, candidates, out_dir)
    if not candidates:
        raise YtdlpError(
            "yt-dlp produced no audio (no match, or the video exceeds "
            f"{max_duration_s}s): {stderr[-200:] or 'no output'}"
        )
    return candidates[0]


def _existing_or_glob(candidates: list[Path], out_dir: Path) -> list[Path]:
    return [p for p in candidates if p.exists()] or sorted(out_dir.glob("*.wav"))
