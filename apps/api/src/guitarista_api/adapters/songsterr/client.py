"""HTTP client for the unofficial Songsterr API.

Endpoints (verified live 2026-09-11; may change without notice):

* ``GET https://www.songsterr.com/api/songs?pattern=<q>``      -> ``[SearchResult]``
* ``GET https://www.songsterr.com/api/meta/<songId>``          -> ``Meta`` (revision, image, tracks)
* ``GET https://dqsljvtekg760.cloudfront.net/<songId>/<revisionId>/<image>/<trackIdx>.json``
  -> ``TrackJson`` (gzip on the wire; httpx decodes transparently)
"""

from __future__ import annotations

import httpx
import structlog
from pydantic import TypeAdapter, ValidationError

from guitarista_api.adapters.http import request_with_retry
from guitarista_api.adapters.songsterr.schema import Meta, SearchResult, TrackJson

log = structlog.get_logger(__name__)

BASE_URL = "https://www.songsterr.com"
CDN_URL = "https://dqsljvtekg760.cloudfront.net"

_search_adapter = TypeAdapter(list[SearchResult])


class SongsterrError(Exception):
    """Transport/decoding problem talking to Songsterr; ``status`` set for HTTP errors."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SongsterrClient:
    def __init__(
        self, http: httpx.AsyncClient, *, base_url: str = BASE_URL, cdn_url: str = CDN_URL
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.cdn_url = cdn_url.rstrip("/")

    def track_url(self, song_id: int, revision_id: int, image: str, track_index: int) -> str:
        return f"{self.cdn_url}/{song_id}/{revision_id}/{image}/{track_index}.json"

    async def search(self, pattern: str) -> list[SearchResult]:
        url = f"{self.base_url}/api/songs"
        data = await self._get_json(url, params={"pattern": pattern})
        try:
            return _search_adapter.validate_python(data)
        except ValidationError as exc:
            raise SongsterrError(f"unexpected search payload: {exc.errors()[:1]}") from exc

    async def meta(self, song_id: int) -> Meta:
        data = await self._get_json(f"{self.base_url}/api/meta/{song_id}")
        try:
            return Meta.model_validate(data)
        except ValidationError as exc:
            raise SongsterrError(f"unexpected meta payload: {exc.errors()[:1]}") from exc

    async def track(
        self, song_id: int, revision_id: int, image: str, track_index: int
    ) -> TrackJson:
        data = await self._get_json(self.track_url(song_id, revision_id, image, track_index))
        try:
            return TrackJson.model_validate(data)
        except ValidationError as exc:
            raise SongsterrError(f"unexpected track payload: {exc.errors()[:1]}") from exc

    async def _get_json(self, url: str, **kwargs: object) -> object:
        try:
            response = await request_with_retry(self.http, "GET", url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPStatusError as exc:
            raise SongsterrError(
                f"Songsterr returned HTTP {exc.response.status_code}",
                status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise SongsterrError(f"Songsterr unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise SongsterrError(
                f"Songsterr returned HTTP {response.status_code} for {url}",
                status=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SongsterrError("Songsterr returned non-JSON content") from exc
