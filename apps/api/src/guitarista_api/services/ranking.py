"""Deterministic candidate ranking with rapidfuzz.

Scores are 0..1. The query side is the resolved ``Song`` (title/artist may come from Spotify or
from a raw string, in which case ``artist`` can be empty); the candidate side is whatever a
source returned. Sorting is stable so equal scores keep the source's own order (Songsterr returns
popularity-ordered results).
"""

from __future__ import annotations

from rapidfuzz import fuzz

from guitarista_api.domain.song import Song, SongCandidate
from guitarista_api.services.normalize import normalize_text, normalize_title, normalized_query

CONFIDENT_SCORE = 0.75
"""Top candidate is accepted without LLM help at or above this score."""
AMBIGUOUS_GAP = 0.05
"""Top two within this gap count as ambiguous (LLM re-rank hook)."""


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a, b) / 100.0


def score_candidate(song: Song, candidate: Song) -> float:
    q_title = normalize_text(normalize_title(song.title))
    q_artist = normalize_text(song.artist)
    c_title = normalize_text(normalize_title(candidate.title))
    c_artist = normalize_text(candidate.artist)
    full = _ratio(song.normalized_query, normalized_query(candidate.title, candidate.artist))
    if not q_artist:
        # Raw "oasis wonderwall"-style queries: the whole string is in the title slot.
        return round(max(full, _ratio(q_title, f"{c_artist} {c_title}")), 4)
    title = _ratio(q_title, c_title)
    artist = _ratio(q_artist, c_artist)
    return round(0.5 * full + 0.3 * title + 0.2 * artist, 4)


def rank_candidates(song: Song, candidates: list[SongCandidate]) -> list[SongCandidate]:
    """Return candidates re-scored against ``song`` and sorted best-first (stable)."""
    scored = [c.model_copy(update={"score": score_candidate(song, c.song)}) for c in candidates]
    return sorted(scored, key=lambda c: -c.score)


def is_ambiguous(ranked: list[SongCandidate]) -> bool:
    if not ranked:
        return False
    if ranked[0].score < CONFIDENT_SCORE:
        return True
    return len(ranked) > 1 and ranked[0].score - ranked[1].score < AMBIGUOUS_GAP
