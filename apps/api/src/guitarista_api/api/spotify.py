"""Spotify user login (Authorization Code + PKCE) for noodle mode.

Single user, local machine: there is no session cookie. The browser is sent to Spotify, comes back
to the loopback ``/callback``, and the grant is written to SQLite. The in-flight ``state`` →
``code_verifier`` pairs live in ``app.state.spotify_pkce`` and expire after ten minutes.
"""

from __future__ import annotations

import secrets
import time

import structlog
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from guitarista_api.adapters.spotify import SpotifyError
from guitarista_api.adapters.spotify_user import (
    SCOPES,
    SpotifyUserClient,
    build_authorize_url,
    exchange_code,
    make_code_verifier,
)
from guitarista_api.db.repos_noodle import SpotifyAuthRepo
from guitarista_api.deps import (
    HttpDep,
    SessionFactoryDep,
    SettingsDep,
    SpotifyUserDep,
)
from guitarista_api.domain.noodle import SpotifyStatus
from guitarista_api.errors import ApiError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/spotify", tags=["spotify"])

PKCE_TTL_SECONDS = 600
"""How long a ``/login`` handout stays usable before the callback must be abandoned."""


class LoginResponse(BaseModel):
    authorize_url: str = Field(description="Send the browser here to grant access")
    scopes: list[str] = Field(default_factory=lambda: list(SCOPES))


def _pkce_store(request: Request) -> dict[str, tuple[str, float]]:
    store: dict[str, tuple[str, float]] | None = getattr(request.app.state, "spotify_pkce", None)
    if store is None:
        store = {}
        request.app.state.spotify_pkce = store
    now = time.monotonic()
    for state, (_, expires) in list(store.items()):
        if expires <= now:
            store.pop(state, None)
    return store


async def _toggle_prefetcher(request: Request, action: str) -> None:
    """Nudge the (optional) noodle prefetcher; it is wired up in a later step."""
    prefetcher = getattr(request.app.state, "noodle_prefetcher", None)
    method = getattr(prefetcher, action, None) if prefetcher is not None else None
    if method is None:
        return
    try:
        result = method()
        if hasattr(result, "__await__"):
            await result
    except Exception:  # pragma: no cover - the prefetcher must never break auth
        log.warning("noodle.prefetcher_toggle_failed", action=action, exc_info=True)


@router.get("/login", response_model=LoginResponse)
async def spotify_login(request: Request, settings: SettingsDep) -> LoginResponse:
    """Build the PKCE authorize URL; the client navigates to it."""
    if not settings.spotify_user_enabled:
        raise ApiError("GUITARISTA_SPOTIFY_CLIENT_ID is not configured", status=409)
    state = secrets.token_urlsafe(16)
    verifier = make_code_verifier()
    _pkce_store(request)[state] = (verifier, time.monotonic() + PKCE_TTL_SECONDS)
    return LoginResponse(
        authorize_url=build_authorize_url(
            client_id=settings.spotify_client_id,
            redirect_uri=settings.spotify_redirect_uri,
            state=state,
            code_verifier=verifier,
        ),
        scopes=list(SCOPES),
    )


@router.get("/callback", include_in_schema=False)
async def spotify_callback(
    request: Request,
    settings: SettingsDep,
    http: HttpDep,
    spotify_user: SpotifyUserDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Spotify redirects here. Always bounces the browser back to the web app."""

    def back(reason: str | None = None) -> RedirectResponse:
        suffix = "?spotify=connected" if reason is None else f"?spotify=error&reason={reason}"
        return RedirectResponse(f"{settings.web_base_url.rstrip('/')}/settings{suffix}", 303)

    if error:
        return back(error)
    verifier = _pkce_store(request).pop(state or "", (None, 0.0))[0]
    if not code or verifier is None:
        return back("invalid_state")
    if spotify_user is None:
        return back("not_configured")
    try:
        tokens = await exchange_code(
            http,
            client_id=settings.spotify_client_id,
            code=code,
            redirect_uri=settings.spotify_redirect_uri,
            code_verifier=verifier,
        )
        await spotify_user.save_tokens(tokens)
        profile = await spotify_user.me()
        await spotify_user.save_tokens(tokens, profile=profile)
        log.info("spotify.connected", user=profile.get("id"))
    except SpotifyError as exc:
        log.warning("spotify.callback_failed", error=str(exc))
        return back("exchange_failed")
    await _toggle_prefetcher(request, "start")
    return back()


@router.get("/status", response_model=SpotifyStatus)
async def spotify_status(
    settings: SettingsDep, session_factory: SessionFactoryDep
) -> SpotifyStatus:
    async with session_factory() as session:
        row = await SpotifyAuthRepo(session).get()
    if row is None:
        return SpotifyStatus(connected=False, configured=settings.spotify_user_enabled)
    return SpotifyStatus(
        connected=True,
        display_name=row.display_name,
        spotify_user_id=row.spotify_user_id,
        scopes=(row.scope or "").split(),
        expires_at=row.expires_at,
        configured=settings.spotify_user_enabled,
    )


@router.delete("/auth", status_code=204, response_class=Response)
async def spotify_disconnect(
    request: Request,
    session_factory: SessionFactoryDep,
    spotify_user: SpotifyUserDep,
) -> Response:
    """Forget the grant and stop any background prefetching."""
    await _toggle_prefetcher(request, "stop")
    if isinstance(spotify_user, SpotifyUserClient):
        await spotify_user.forget()
    else:
        async with session_factory() as session:
            await SpotifyAuthRepo(session).delete()
    return Response(status_code=204)
