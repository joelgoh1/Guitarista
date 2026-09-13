"""Shared httpx client + small retry helper.

One ``AsyncClient`` lives on ``app.state.http`` for the whole process (connection pooling,
consistent headers) and is injected into adapters through ``deps.HttpDep``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

RETRY_STATUSES = frozenset({500, 502, 503, 504})


def make_http_client(
    *, timeout: float = 15.0, headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={**DEFAULT_HEADERS, **(headers or {})},
        timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        follow_redirects=True,
    )


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff: float = 0.3,
    **kwargs: Any,
) -> httpx.Response:
    """Send a request, retrying transport errors and 5xx responses ``retries`` times.

    Retries use a small exponential backoff; the last failure is raised (``httpx.HTTPStatusError``
    for 5xx after ``raise_for_status``, ``httpx.TransportError`` for connection problems). Non-5xx
    error statuses are returned to the caller untouched so it can decide (404 = not found, etc.).
    """
    attempt = 0
    while True:
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt >= retries:
                raise
            log.warning("http.retry", url=url, attempt=attempt + 1, error=str(exc))
        else:
            if response.status_code not in RETRY_STATUSES:
                return response
            if attempt >= retries:
                response.raise_for_status()
                return response
            log.warning("http.retry", url=url, attempt=attempt + 1, status=response.status_code)
        await asyncio.sleep(backoff * (2**attempt))
        attempt += 1
