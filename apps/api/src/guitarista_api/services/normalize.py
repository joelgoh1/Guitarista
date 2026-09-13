"""Pure text normalization for song titles/artists and search queries (no I/O)."""

from __future__ import annotations

import re
import unicodedata

_PAREN_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*"
    r"(remaster(ed)?|live|feat\.?|ft\.?|featuring|version|edit|mix|remix|mono|stereo|"
    r"deluxe|bonus|acoustic|demo|single|album|radio|explicit|clean|anniversary|"
    r"from\s|soundtrack|\d{4})"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_DASH_NOISE = re.compile(
    r"\s+-\s+(remaster(ed)?|live|feat\.?|ft\.?|version|edit|mix|remix|mono|stereo|"
    r"deluxe|bonus|acoustic|demo|single|radio|explicit|anniversary|\d{4}).*$",
    re.IGNORECASE,
)
_FEAT_TAIL = re.compile(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
_NON_WORD = re.compile(r"[^a-z0-9\s]+")
_SPACES = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize_text(text: str) -> str:
    """Lowercase ASCII words only, single-spaced. ``&`` becomes ``and`` for artist matching."""
    text = strip_accents(text).lower().replace("&", " and ")
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """Drop release-noise like ``- Remastered 2014``, ``(feat. X)``, ``[Live]`` from a title.

    Returns the cleaned title with original casing, single-spaced; falls back to the input when
    stripping would leave nothing.
    """
    cleaned = _PAREN_NOISE.sub("", title)
    cleaned = _DASH_NOISE.sub("", cleaned)
    cleaned = _FEAT_TAIL.sub("", cleaned)
    cleaned = _SPACES.sub(" ", cleaned).strip(" -")
    return cleaned or title.strip()


def normalized_query(title: str, artist: str | None) -> str:
    """Canonical dedupe/search key: ``"<artist> <title>"`` normalized, artist optional."""
    parts = [normalize_text(artist or ""), normalize_text(normalize_title(title))]
    return " ".join(p for p in parts if p)
