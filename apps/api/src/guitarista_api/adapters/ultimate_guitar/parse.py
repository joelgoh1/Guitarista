"""Pull the embedded page state out of Ultimate Guitar HTML.

UG server-renders its React state into ``<div class="js-store" data-content="{html-escaped
JSON}">`` (current) or ``window.UGAPP.store.page = {...};`` (legacy). Both shapes are normalized to
a ``store`` dict with a ``page.data`` subtree:

* search page:  ``store.page.data.results[]`` with ``id, song_name, artist_name, type, rating,
  votes, tab_url, tuning`` (official/pro rows have ``id: null`` and are skipped)
* tab page:     ``store.page.data.tab`` (metadata) + ``tab_view.meta`` (tuning/capo/tonality) +
  ``tab_view.wiki_tab.content`` (``[ch]``/``[tab]`` markup)

Cloudflare interstitials ("Just a moment...", ``cf-challenge``) raise ``UGBlockedError`` from the
client; ``is_blocked`` is the detector.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from guitarista_api.sources.base import SourceError

_JS_STORE_RE = re.compile(
    r"""class=["']js-store["'][^>]*?data-content=(?:"([^"]*)"|'([^']*)')""", re.DOTALL
)
_JS_STORE_RE_ALT = re.compile(
    r"""data-content=(?:"([^"]*)"|'([^']*)')[^>]*?class=["']js-store["']""", re.DOTALL
)
_UGAPP_RE = re.compile(
    r"window\.UGAPP\.store\.page\s*=\s*(\{.*?\})\s*;\s*(?:\n|</script>)", re.DOTALL
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

BLOCKED_MARKERS = ("cf-challenge", "cf_chl_", "challenge-platform", "cf-browser-verification")


class UGParseError(Exception):
    """The HTML did not contain a recognizable UG store."""


class UGBlockedError(SourceError):
    """Cloudflare / captcha interstitial instead of the page (also a ``SourceError``)."""

    def __init__(self, url: str | None = None) -> None:
        super().__init__("Ultimate Guitar blocked the request", {"url": url} if url else {})


def is_blocked(page_html: str) -> bool:
    head = page_html[:20000]
    title = _TITLE_RE.search(head)
    if title and "just a moment" in html.unescape(title.group(1)).strip().lower():
        return True
    low = head.lower()
    return any(marker in low for marker in BLOCKED_MARKERS) and "js-store" not in low


def extract_store(page_html: str) -> dict[str, Any]:
    """Return the UG ``store`` dict (``store["page"]["data"]`` holds the payload)."""
    if is_blocked(page_html):
        raise UGBlockedError()
    match = _JS_STORE_RE.search(page_html) or _JS_STORE_RE_ALT.search(page_html)
    if match:
        try:
            data = json.loads(html.unescape(match.group(1) or match.group(2) or ""))
        except json.JSONDecodeError as exc:
            raise UGParseError(f"js-store payload is not JSON: {exc}") from exc
        store = data.get("store", data) if isinstance(data, dict) else None
        if isinstance(store, dict) and isinstance(store.get("page"), dict):
            return store
        raise UGParseError("js-store payload has no page state")
    legacy = _UGAPP_RE.search(page_html)
    if legacy:
        try:
            page = json.loads(legacy.group(1))
        except json.JSONDecodeError as exc:
            raise UGParseError(f"UGAPP store is not JSON: {exc}") from exc
        return {"page": page}
    raise UGParseError("no UG store found in page (layout changed?)")


def page_data(store: dict[str, Any]) -> dict[str, Any]:
    data = store.get("page", {}).get("data")
    if not isinstance(data, dict):
        raise UGParseError("UG store has no page.data")
    return data


# --------------------------------------------------------------------------- models


class UGResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    song_name: str
    artist_name: str
    type: str
    rating: float | None = None
    votes: int | None = None
    tab_url: str
    tuning: str | None = None
    version: int | None = None


class UGTabPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    song_name: str
    artist_name: str
    type: str
    tab_url: str | None = None
    tuning_name: str | None = None
    tuning_value: str | None = Field(default=None, description='e.g. "E A D G B E" (low → high)')
    capo: int | None = None
    tonality: str | None = None
    difficulty: str | None = None
    content: str = ""

    @property
    def is_chords(self) -> bool:
        return self.type.lower() == "chords"


def parse_search_results(store: dict[str, Any]) -> list[UGResult]:
    """All rows with a numeric id (skips official/pro rows, which link to the Pro player)."""
    data = page_data(store)
    rows = data.get("results") or []
    out: list[UGResult] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("id") is None or not row.get("tab_url"):
            continue
        if not row.get("type"):
            continue
        out.append(
            UGResult(
                id=int(row["id"]),
                song_name=str(row.get("song_name") or ""),
                artist_name=str(row.get("artist_name") or ""),
                type=str(row["type"]),
                rating=_float_or_none(row.get("rating")),
                votes=_int_or_none(row.get("votes")),
                tab_url=str(row["tab_url"]),
                tuning=row.get("tuning") or None,
                version=_int_or_none(row.get("version")),
            )
        )
    return out


def parse_tab_page(store: dict[str, Any]) -> UGTabPage:
    data = page_data(store)
    tab = data.get("tab") or {}
    view = data.get("tab_view") or {}
    meta = view.get("meta") or {}
    if not isinstance(meta, dict):  # UG sometimes serializes an empty meta as []
        meta = {}
    tuning = meta.get("tuning") or {}
    if not isinstance(tuning, dict):
        tuning = {}
    content = (view.get("wiki_tab") or {}).get("content") or ""
    if not tab.get("id"):
        raise UGParseError("UG page has no tab metadata")
    capo = _int_or_none(meta.get("capo"))
    if capo is None:
        capo = _int_or_none(tab.get("capo"))
    return UGTabPage(
        id=int(tab["id"]),
        song_name=str(tab.get("song_name") or ""),
        artist_name=str(tab.get("artist_name") or ""),
        type=str(tab.get("type") or "Tabs"),
        tab_url=tab.get("tab_url"),
        tuning_name=tuning.get("name") or tab.get("tuning") or None,
        tuning_value=tuning.get("value") or None,
        capo=capo,
        tonality=meta.get("tonality") or tab.get("tonality_name") or None,
        difficulty=meta.get("difficulty") or None,
        content=str(content).replace("\r\n", "\n").replace("\r", "\n"),
    )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
