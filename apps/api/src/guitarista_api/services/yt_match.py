"""Pick the YouTube search hit that actually is the song (pure, no I/O).

``ytsearch1`` blindly trusts YouTube's top result, which is how a cover, a live cut or a ten-hour
loop ends up transcribed as if it were the studio track. This module scores several hits against
the resolved :class:`Song` -- text similarity plus, crucially, agreement with Spotify's known
duration -- and refuses to pick anything that does not clear a threshold.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from guitarista_api.adapters.ytdlp import YtCandidate
from guitarista_api.domain.song import Song
from guitarista_api.services.normalize import normalize_text, normalize_title
from guitarista_api.services.ranking import score_candidate

DURATION_EXACT_S = 3.0
"""Duration deltas at or below this score full marks."""
DURATION_ZERO_S = 25.0
"""Duration deltas at or above this score zero (but are not yet rejected).

Official music videos routinely carry an intro/outro the album track does not -- the Wonderwall
video is 278s against a 259s album cut -- so the window has to tolerate ~20s without zeroing."""
DURATION_REJECT_S = 45.0
"""Beyond this delta the hit is a different recording; drop it outright."""

ACCEPT_SCORE = 0.55
"""Minimum combined score when the durations could be compared."""
ACCEPT_SCORE_TEXT_ONLY = 0.7
"""Stricter bar when no duration is known on either side -- text is all we have."""
MIN_TEXT_SCORE = 0.45
"""Floor on title agreement. Plenty of unrelated tracks are the same length, so duration may
corroborate a title match but must never substitute for one."""

DURATION_WEIGHT = 0.4
TEXT_WEIGHT = 0.6

LIVE_PENALTY = 0.3
KEYWORD_PENALTY = 0.25
MAX_KEYWORD_PENALTY = 0.5

_VARIANT_KEYWORDS = (
    "live",
    "cover",
    "remix",
    "karaoke",
    "instrumental",
    "backing track",
    "sped up",
    "slowed",
    "nightcore",
    "8d",
    "reaction",
    "tutorial",
    "lesson",
)
"""Words that mark a *different* recording -- penalized unless the song itself has them."""

_YT_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*"
    r"(official|video|audio|lyric|lyrics|hd|hq|4k|mv|m/v|visualizer|full album|with lyrics)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_UPLOADER_NOISE = re.compile(r"(\s*-\s*topic|vevo|official|music|records)\s*$", re.IGNORECASE)
_SPLIT_DASH = re.compile(r"\s+[-–—]\s+")


def clean_yt_title(title: str) -> str:
    """Strip YouTube packaging (``(Official Video)``, ``[HD]``) then the usual release noise."""
    return normalize_title(_YT_TITLE_NOISE.sub("", title))


def clean_uploader(uploader: str) -> str:
    """``ArtistVEVO`` / ``Artist - Topic`` -> ``Artist``."""
    return _UPLOADER_NOISE.sub("", uploader).strip(" -") or uploader.strip()


def _text_score(song: Song, cand: YtCandidate) -> float:
    """Best fuzz score over the plausible readings of a YouTube title.

    Channel names are unreliable (``Artist - Topic``, a random uploader), and titles are usually
    ``Artist - Title``, so try both and keep whichever agrees more.
    """
    title = clean_yt_title(cand.title)
    artist = clean_uploader(cand.uploader)
    readings = [Song(id="yt", title=title or cand.title, artist=artist)]
    parts = _SPLIT_DASH.split(title, maxsplit=1)
    if len(parts) == 2 and all(p.strip() for p in parts):
        left, right = parts[0].strip(), parts[1].strip()
        readings.append(Song(id="yt", title=right, artist=left))
    return max(score_candidate(song, reading) for reading in readings)


def _duration_score(song: Song, cand: YtCandidate) -> tuple[float | None, float | None]:
    """``(score, delta)``; ``(None, None)`` when either duration is unknown."""
    if not song.duration_s or not cand.duration_s:
        return None, None
    delta = abs(song.duration_s - cand.duration_s)
    if delta <= DURATION_EXACT_S:
        return 1.0, delta
    if delta >= DURATION_ZERO_S:
        return 0.0, delta
    span = DURATION_ZERO_S - DURATION_EXACT_S
    return round(1.0 - (delta - DURATION_EXACT_S) / span, 4), delta


def _channel_match(song: Song, cand: YtCandidate) -> float:
    """How well the channel name matches the artist -- the "official upload" signal.

    Used only to break ties between otherwise equal hits, so a re-upload with the same title
    does not beat the artist's own channel purely on search order.
    """
    artist = normalize_text(song.artist)
    channel = normalize_text(clean_uploader(cand.uploader))
    if not artist or not channel:
        return 0.0
    return round(fuzz.token_set_ratio(artist, channel) / 100.0, 4)


def _keyword_penalty(song: Song, cand: YtCandidate) -> tuple[float, list[str]]:
    """Penalize variant markers in the hit's title that the song's own title does not have."""
    hay = normalize_text(cand.title)
    song_words = normalize_text(song.title)
    hits = [kw for kw in _VARIANT_KEYWORDS if kw in hay and kw not in song_words]
    penalty = min(MAX_KEYWORD_PENALTY, KEYWORD_PENALTY * len(hits))
    return penalty, hits


def score_yt_candidate(song: Song, cand: YtCandidate) -> tuple[float, dict[str, Any]]:
    """Score ``cand`` in 0..1 and return a breakdown for the tier log.

    ``breakdown["rejected"]`` is set when the durations disagree so badly that this cannot be the
    same recording; such a candidate is never picked regardless of its score.
    """
    text = _text_score(song, cand)
    duration, delta = _duration_score(song, cand)
    penalty, keywords = _keyword_penalty(song, cand)
    if cand.is_live and "live" not in normalize_text(song.title):
        penalty = min(1.0, penalty + LIVE_PENALTY)

    if duration is None:
        score = text - penalty
    else:
        score = TEXT_WEIGHT * text + DURATION_WEIGHT * duration - penalty
    score = round(max(0.0, min(1.0, score)), 4)

    breakdown: dict[str, Any] = {
        "video_id": cand.video_id,
        "title": cand.title,
        "uploader": cand.uploader,
        "duration_s": cand.duration_s,
        "text_score": round(text, 4),
        "duration_score": duration,
        "duration_delta_s": round(delta, 2) if delta is not None else None,
        "penalty": round(penalty, 4),
        "keywords": keywords,
        "channel_match": _channel_match(song, cand),
        "score": score,
    }
    if delta is not None and delta > DURATION_REJECT_S:
        breakdown["rejected"] = (
            f"duration off by {delta:.0f}s (expected {song.duration_s:.0f}s, "
            f"got {cand.duration_s:.0f}s)"
        )
    elif text < MIN_TEXT_SCORE:
        breakdown["rejected"] = f"title does not match (text score {text:.2f})"
    elif cand.is_live and "live" not in normalize_text(song.title):
        breakdown["live"] = True
    return score, breakdown


def pick_best(
    song: Song, candidates: list[YtCandidate]
) -> tuple[YtCandidate | None, list[dict[str, Any]]]:
    """Return the best acceptable candidate (or ``None``) plus every candidate's breakdown.

    Breakdowns come back sorted best-first so the caller can explain the decision -- including
    why nothing was good enough.
    """
    scored: list[tuple[float, YtCandidate, dict[str, Any]]] = []
    for cand in candidates:
        score, breakdown = score_yt_candidate(song, cand)
        scored.append((score, cand, breakdown))
    # Equal scores break toward the artist's own channel, then toward search order (stable sort).
    scored.sort(key=lambda item: (-item[0], -item[2]["channel_match"]))
    breakdowns = [item[2] for item in scored]

    # No duration to check against means text similarity carries the whole decision.
    threshold = ACCEPT_SCORE if song.duration_s else ACCEPT_SCORE_TEXT_ONLY
    for score, cand, breakdown in scored:
        if breakdown.get("rejected"):
            continue
        if score >= threshold:
            breakdown["chosen"] = True
            return cand, breakdowns
    return None, breakdowns


def rejection_message(song: Song, breakdowns: list[dict[str, Any]]) -> str:
    """Explain why no candidate was accepted, naming the closest miss."""
    if not breakdowns:
        return "no YouTube results for this song"
    top = breakdowns[0]
    expected = f"{song.duration_s:.0f}s" if song.duration_s else "unknown duration"
    reason = top.get("rejected") or f"best score {top['score']:.2f} below threshold"
    return (
        f"no YouTube result confidently matched (expected {expected}); "
        f"closest was {top['title']!r} by {top['uploader'] or 'unknown'} -- {reason}. "
        "Upload the audio or pass audio_url to choose the recording yourself."
    )
