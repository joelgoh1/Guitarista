"""Spotify Web API (client-credentials flow): track lookup + search, URL/URI parsing."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from guitarista_api.adapters.http import request_with_retry
from guitarista_api.domain.song import Song
from guitarista_api.services.normalize import normalize_title

log = structlog.get_logger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"

_TRACK_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?track/|spotify:track:)([A-Za-z0-9]{22})"
)


def parse_spotify_track_id(text: str | None) -> str | None:
    """Extract a track id from ``open.spotify.com/track/<id>`` or ``spotify:track:<id>``."""
    if not text:
        return None
    match = _TRACK_RE.search(text.strip())
    return match.group(1) if match else None


class SpotifyError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SpotifyTrack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    artists: list[str] = Field(default_factory=list)
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    artwork_url: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SpotifyTrack:
        album = data.get("album") or {}
        images = album.get("images") or []
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            artists=[a.get("name", "") for a in data.get("artists", []) if a.get("name")],
            album=album.get("name"),
            duration_ms=data.get("duration_ms"),
            isrc=(data.get("external_ids") or {}).get("isrc"),
            artwork_url=images[0]["url"] if images else None,
        )

    def to_song(self) -> Song:
        return Song(
            id=f"spotify_{self.id}",
            title=normalize_title(self.name),
            artist=", ".join(self.artists),
            album=self.album,
            duration_s=self.duration_ms / 1000 if self.duration_ms else None,
            spotify_id=self.id,
            isrc=self.isrc,
            artwork_url=self.artwork_url,
        )


class SpotifyClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        *,
        token_url: str = TOKEN_URL,
        api_url: str = API_URL,
    ) -> None:
        self.http = http
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.api_url = api_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token
        try:
            response = await request_with_retry(
                self.http,
                "POST",
                self.token_url,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
        except httpx.HTTPError as exc:
            raise SpotifyError(f"Spotify token request failed: {exc}") from exc
        if response.status_code >= 400:
            raise SpotifyError(
                f"Spotify token request failed (HTTP {response.status_code})",
                status=response.status_code,
            )
        body = response.json()
        self._token = str(body["access_token"])
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 3600))
        return self._token

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        token = await self._get_token()
        try:
            response = await request_with_retry(
                self.http,
                "GET",
                f"{self.api_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise SpotifyError(f"Spotify request failed: {exc}") from exc
        if response.status_code == 401:
            self._token = None  # force refresh next time
        if response.status_code >= 400:
            raise SpotifyError(
                f"Spotify returned HTTP {response.status_code} for {path}",
                status=response.status_code,
            )
        data: dict[str, Any] = response.json()
        return data

    async def track(self, track_id: str) -> SpotifyTrack:
        return SpotifyTrack.from_api(await self._get(f"/tracks/{track_id}"))

    async def search(
        self, title: str, artist: str | None = None, *, limit: int = 5
    ) -> list[SpotifyTrack]:
        q = f"track:{title} artist:{artist}" if artist else title
        data = await self._get("/search", q=q, type="track", limit=limit)
        items = (data.get("tracks") or {}).get("items") or []
        return [SpotifyTrack.from_api(item) for item in items]
