"""Spotify Web API as *the user* (Authorization Code + PKCE, no client secret).

Single-user and local: the grant lives in one SQLite row (``spotify_auth``) and the refresh token
is rotated in place every time Spotify hands us a new one. Everything here is additive on top of
:class:`~guitarista_api.adapters.spotify.SpotifyClient`; the client-credentials client stays the
one used for plain track lookup/search.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.http import request_with_retry
from guitarista_api.adapters.spotify import (
    API_URL,
    TOKEN_URL,
    SpotifyClient,
    SpotifyError,
    SpotifyTrack,
)
from guitarista_api.db.repos_noodle import SpotifyAuthRepo

log = structlog.get_logger(__name__)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"

SCOPES = ("user-top-read", "user-read-recently-played", "user-library-read")
"""Read-only history scopes. Nothing here can modify the user's Spotify account."""

TimeRange = Literal["short_term", "medium_term", "long_term"]

PAGE_LIMIT = 50
"""Spotify's hard cap for these endpoints (recently-played is capped at 50 items total)."""


class SpotifyNotConnected(SpotifyError):
    """No Spotify user grant is stored yet."""

    def __init__(self, message: str = "Spotify is not connected") -> None:
        super().__init__(message, status=401)


def make_code_verifier() -> str:
    """A 64-char RFC 7636 code verifier."""
    return secrets.token_urlsafe(48)[:64]


def code_challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_verifier: str,
    scopes: tuple[str, ...] = SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(scopes),
        "code_challenge_method": "S256",
        "code_challenge": code_challenge_for(code_verifier),
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(
    http: httpx.AsyncClient,
    *,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    token_url: str = TOKEN_URL,
) -> dict[str, Any]:
    """Swap an authorization ``code`` for tokens. Raises :class:`SpotifyError` on rejection."""
    try:
        response = await request_with_retry(
            http,
            "POST",
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            },
        )
    except httpx.HTTPError as exc:
        raise SpotifyError(f"Spotify token exchange failed: {exc}") from exc
    if response.status_code >= 400:
        raise SpotifyError(
            f"Spotify rejected the authorization code (HTTP {response.status_code})",
            status=response.status_code,
        )
    body: dict[str, Any] = response.json()
    if not body.get("refresh_token"):
        raise SpotifyError("Spotify returned no refresh token")
    return body


class SpotifyUserClient(SpotifyClient):
    """Reads the signed-in user's listening history, refreshing tokens from SQLite as needed."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        client_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        token_url: str = TOKEN_URL,
        api_url: str = API_URL,
        max_retries: int = 2,
        max_retry_sleep: float = 10.0,
    ) -> None:
        super().__init__(http, client_id, "", token_url=token_url, api_url=api_url)
        self.session_factory = session_factory
        self.max_retries = max_retries
        self.max_retry_sleep = max_retry_sleep
        self._refresh_lock = asyncio.Lock()

    # -- auth ---------------------------------------------------------------

    async def is_connected(self) -> bool:
        async with self.session_factory() as session:
            return await SpotifyAuthRepo(session).get() is not None

    async def save_tokens(
        self, body: dict[str, Any], *, profile: dict[str, Any] | None = None
    ) -> None:
        """Persist a token payload (from an exchange or a refresh) and cache it in memory."""
        expires_in = float(body.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        async with self.session_factory() as session:
            await SpotifyAuthRepo(session).upsert(
                refresh_token=body.get("refresh_token"),
                access_token=body.get("access_token"),
                expires_at=expires_at,
                scope=body.get("scope"),
                spotify_user_id=(profile or {}).get("id"),
                display_name=(profile or {}).get("display_name"),
            )
        self._token = str(body["access_token"])
        self._token_expires_at = time.monotonic() + expires_in

    async def forget(self) -> bool:
        """Drop the stored grant and the cached access token."""
        self._token = None
        self._token_expires_at = 0.0
        async with self.session_factory() as session:
            return await SpotifyAuthRepo(session).delete()

    async def _get_token(self, *, force: bool = False) -> str:
        if not force and self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token
        async with self._refresh_lock:
            if not force and self._token and time.monotonic() < self._token_expires_at - 30:
                return self._token
            async with self.session_factory() as session:
                row = await SpotifyAuthRepo(session).get()
                if row is None:
                    raise SpotifyNotConnected()
                refresh_token = row.refresh_token
                stored_access, stored_expiry = row.access_token, row.expires_at
            # A token persisted by another process (or a previous run) may still be good.
            if not force and stored_access and stored_expiry is not None:
                expiry = (
                    stored_expiry if stored_expiry.tzinfo else stored_expiry.replace(tzinfo=UTC)
                )
                remaining = (expiry - datetime.now(UTC)).total_seconds()
                if remaining > 60:
                    self._token = stored_access
                    self._token_expires_at = time.monotonic() + remaining
                    return self._token
            body = await self._refresh(refresh_token)
            await self.save_tokens(body)
            assert self._token is not None
            return self._token

    async def _refresh(self, refresh_token: str) -> dict[str, Any]:
        try:
            response = await request_with_retry(
                self.http,
                "POST",
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                },
            )
        except httpx.HTTPError as exc:
            raise SpotifyError(f"Spotify token refresh failed: {exc}") from exc
        if response.status_code >= 400:
            raise SpotifyError(
                f"Spotify token refresh failed (HTTP {response.status_code})",
                status=response.status_code,
            )
        body: dict[str, Any] = response.json()
        if not body.get("access_token"):
            raise SpotifyError("Spotify token refresh returned no access token")
        # Spotify rotates the refresh token on most refreshes but not all; keep the old one
        # when the response omits it so the grant never ends up blank.
        body.setdefault("refresh_token", refresh_token)
        return body

    # -- requests -----------------------------------------------------------

    def _retry_after(self, response: httpx.Response, attempt: int) -> float:
        raw = response.headers.get("Retry-After")
        try:
            delay = float(raw) if raw is not None else 0.0
        except ValueError:
            delay = 0.0
        return min(max(delay, 0.5 * (2**attempt)), self.max_retry_sleep)

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        """Like the base client, but retries 429s for ``Retry-After`` seconds (bounded)."""
        attempt = 0
        force = False
        while True:
            token = await self._get_token(force=force)
            force = False
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
            if response.status_code == 429 and attempt < self.max_retries:
                delay = self._retry_after(response, attempt)
                log.warning("spotify.rate_limited", path=path, sleep=delay, attempt=attempt + 1)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if response.status_code == 401:
                self._token = None  # the access token died early; refresh and try once more
                if attempt < self.max_retries:
                    force = True
                    attempt += 1
                    continue
            if response.status_code >= 400:
                raise SpotifyError(
                    f"Spotify returned HTTP {response.status_code} for {path}",
                    status=response.status_code,
                )
            data: dict[str, Any] = response.json()
            return data

    # -- history ------------------------------------------------------------

    @staticmethod
    def _tracks(items: list[dict[str, Any]]) -> list[SpotifyTrack]:
        """``/me/tracks`` and ``/me/player/recently-played`` nest the track under ``item.track``."""
        out: list[SpotifyTrack] = []
        for item in items:
            data = item.get("track") if isinstance(item.get("track"), dict) else item
            if not isinstance(data, dict) or not data.get("id"):
                continue  # local files and podcast episodes have no track id
            out.append(SpotifyTrack.from_api(data))
        return out

    async def me(self) -> dict[str, Any]:
        return await self._get("/me")

    async def top_tracks(
        self, time_range: TimeRange = "short_term", *, limit: int = PAGE_LIMIT
    ) -> list[SpotifyTrack]:
        data = await self._get("/me/top/tracks", time_range=time_range, limit=limit)
        return self._tracks(data.get("items") or [])

    async def recently_played(self, *, limit: int = PAGE_LIMIT) -> list[SpotifyTrack]:
        """Up to 50 items; duplicates are meaningful (they are repeat plays)."""
        data = await self._get("/me/player/recently-played", limit=limit)
        return self._tracks(data.get("items") or [])

    async def saved_tracks(self, *, pages: int = 3, limit: int = PAGE_LIMIT) -> list[SpotifyTrack]:
        out: list[SpotifyTrack] = []
        for page in range(max(pages, 0)):
            data = await self._get("/me/tracks", limit=limit, offset=page * limit)
            items = data.get("items") or []
            out.extend(self._tracks(items))
            if len(items) < limit or not data.get("next"):
                break
        return out
