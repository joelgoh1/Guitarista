"""Noodle mode endpoints: the listening shelf, a forced refresh and the surprise pick.

Everything here needs a connected Spotify account, so every route answers 409 when there is no
grant. Nothing blocks on the background prefetcher: the pool is served straight from SQLite.
"""

from __future__ import annotations

import asyncio
import random

import structlog
from fastapi import APIRouter, Query, Request, Response

from guitarista_api.adapters.spotify_user import SpotifyUserClient
from guitarista_api.db.repos_noodle import PoolRepo
from guitarista_api.deps import SessionFactoryDep, SettingsDep, SpotifyUserDep
from guitarista_api.domain.noodle import PoolEntry, SurprisePick
from guitarista_api.errors import Conflict, NotFound
from guitarista_api.services.listening_pool import PoolSummary, build_pool

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

VISIBLE_STATUSES = ("new", "checking", "queued", "ready", "failed")
"""Everything except ``dismissed``; unavailable entries are filtered out on top of this."""


async def _connected(spotify_user: SpotifyUserClient | None) -> SpotifyUserClient:
    """The user client, or a 409 explaining that Spotify has to be connected first."""
    if spotify_user is None or not await spotify_user.is_connected():
        raise Conflict("Spotify is not connected; connect it from Settings first")
    return spotify_user


def _refresh_lock(request: Request) -> asyncio.Lock:
    lock: asyncio.Lock | None = getattr(request.app.state, "noodle_refresh_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.noodle_refresh_lock = lock
    return lock


@router.get("", response_model=list[PoolEntry])
async def list_recommendations(
    session_factory: SessionFactoryDep,
    spotify_user: SpotifyUserDep,
    limit: int = Query(default=24, ge=1, le=100),
) -> list[PoolEntry]:
    """The listening pool, best score first, without dismissed or unplayable entries."""
    await _connected(spotify_user)
    async with session_factory() as session:
        entries = await PoolRepo(session).list(statuses=VISIBLE_STATUSES, limit=limit * 4)
    return [e for e in entries if e.availability != "unavailable"][:limit]


@router.post("/refresh", response_model=PoolSummary, status_code=202)
async def refresh_recommendations(
    request: Request,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    spotify_user: SpotifyUserDep,
) -> PoolSummary:
    """Rebuild the pool from Spotify right now (ignores the refresh interval)."""
    client = await _connected(spotify_user)
    lock = _refresh_lock(request)
    if lock.locked():
        raise Conflict("a pool refresh is already running")
    async with lock:
        summary = await build_pool(
            client=client,
            session_factory=session_factory,
            sources=getattr(request.app.state, "sources", []),
            settings=settings,
            force=True,
        )
    prefetcher = getattr(request.app.state, "noodle_prefetcher", None)
    if prefetcher is not None:
        prefetcher.start()
    return summary


@router.post("/{spotify_id}/dismiss", status_code=204, response_class=Response)
async def dismiss_recommendation(
    spotify_id: str,
    session_factory: SessionFactoryDep,
    spotify_user: SpotifyUserDep,
) -> Response:
    """Hide one entry for good; a later refresh will not bring it back."""
    await _connected(spotify_user)
    async with session_factory() as session:
        if not await PoolRepo(session).dismiss(spotify_id):
            raise NotFound(f"{spotify_id!r} is not in the listening pool")
    return Response(status_code=204)


@router.get("/surprise", response_model=SurprisePick)
async def surprise(
    session_factory: SessionFactoryDep,
    spotify_user: SpotifyUserDep,
) -> SurprisePick:
    """A score-weighted random ready tab; failing that, the best entry still to generate."""
    await _connected(spotify_user)
    async with session_factory() as session:
        entries = await PoolRepo(session).list(statuses=VISIBLE_STATUSES, limit=200)
    playable = [e for e in entries if e.availability != "unavailable"]
    ready = [e for e in playable if e.status == "ready" and e.tab_id]
    if ready:
        weights = [max(e.score, 0.01) for e in ready]
        pick = random.choices(ready, weights=weights, k=1)[0]
        return SurprisePick(entry=pick, tab_id=pick.tab_id, reason="ready to play")
    available = [e for e in playable if e.availability == "available"]
    if available:
        return SurprisePick(entry=available[0], tab_id=None, reason="needs generating")
    if playable:
        return SurprisePick(entry=playable[0], tab_id=None, reason="not checked yet")
    raise NotFound("the listening pool is empty; refresh it first")
