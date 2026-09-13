"""HTTP client for Ultimate Guitar's HTML pages (there is no public JSON API).

* ``GET https://www.ultimate-guitar.com/search.php?search_type=title&value=<q>`` -> search page
* ``GET https://tabs.ultimate-guitar.com/tab/<artist>/<slug>-<id>``              -> tab page

Both are server-rendered with the state embedded (see ``parse.py``). UG sits behind Cloudflare and
may answer with a challenge page or 403; that surfaces as ``UGBlockedError`` (a ``SourceError``).
"""

from __future__ import annotations

import httpx
import structlog

from guitarista_api.adapters.http import request_with_retry
from guitarista_api.adapters.ultimate_guitar.parse import (
    UGBlockedError,
    UGParseError,
    UGResult,
    UGTabPage,
    extract_store,
    is_blocked,
    parse_search_results,
    parse_tab_page,
)

log = structlog.get_logger(__name__)

BASE_URL = "https://www.ultimate-guitar.com"
SEARCH_PATH = "/search.php"

_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": BASE_URL + "/",
}


class UGError(Exception):
    """Transport/parse problem talking to Ultimate Guitar; ``status`` set for HTTP errors."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class UGClient:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str = BASE_URL) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    def search_url(self, query: str) -> str:
        return f"{self.base_url}{SEARCH_PATH}"

    async def search(self, query: str, *, page: int | None = None) -> list[UGResult]:
        params: dict[str, str | int] = {"search_type": "title", "value": query}
        if page and page > 1:
            params["page"] = page
        html = await self._get_html(self.search_url(query), params=params)
        try:
            return parse_search_results(extract_store(html))
        except UGParseError as exc:
            raise UGError(f"could not parse UG search page: {exc}") from exc

    async def tab_page(self, url: str) -> UGTabPage:
        html = await self._get_html(url)
        try:
            return parse_tab_page(extract_store(html))
        except UGParseError as exc:
            raise UGError(f"could not parse UG tab page: {exc}") from exc

    async def _get_html(self, url: str, **kwargs: object) -> str:
        try:
            response = await request_with_retry(
                self.http,
                "GET",
                url,
                headers=_HTML_HEADERS,
                **kwargs,  # type: ignore[arg-type]
            )
        except httpx.HTTPStatusError as exc:
            raise UGError(
                f"Ultimate Guitar returned HTTP {exc.response.status_code}",
                status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise UGError(f"Ultimate Guitar unreachable: {exc}") from exc
        text = response.text
        if response.status_code in (403, 429, 503) or is_blocked(text):
            log.warning("ug.blocked", url=url, status=response.status_code)
            raise UGBlockedError(url)
        if response.status_code >= 400:
            raise UGError(
                f"Ultimate Guitar returned HTTP {response.status_code} for {url}",
                status=response.status_code,
            )
        return text
