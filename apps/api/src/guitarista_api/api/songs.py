from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from guitarista_api.adapters.spotify import SpotifyError
from guitarista_api.db.repo import SongRepo
from guitarista_api.deps import HttpDep, LLMDep, SessionFactoryDep, SettingsDep, SpotifyDep
from guitarista_api.domain.candidate import CandidatesRequest, CandidatesResponse
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.errors import ApiError, NotFound, UnprocessableError
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.candidates import collect_candidates
from guitarista_api.services.song_resolver import SongResolveError, SongResolver
from guitarista_api.services.sources_factory import tier_timeouts

router = APIRouter(prefix="/songs", tags=["songs"])


@router.post("/resolve", response_model=Song)
async def resolve_song(
    query: SongQuery, session_factory: SessionFactoryDep, spotify: SpotifyDep
) -> Song:
    """Resolve a link / typed text / title+artist into a Song (Spotify when configured)."""
    try:
        return await SongResolver(session_factory, spotify).resolve(query)
    except SongResolveError as exc:
        raise UnprocessableError(str(exc)) from exc


@router.get("/search", response_model=list[Song])
async def search_songs(
    response: Response,
    spotify: SpotifyDep,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[Song]:
    """Autocomplete via Spotify. Without credentials returns ``[]`` with ``X-Spotify: disabled``."""
    if spotify is None:
        response.headers["X-Spotify"] = "disabled"
        return []
    try:
        hits = await spotify.search(q, None, limit=limit)
    except SpotifyError as exc:
        raise ApiError(f"Spotify search failed: {exc}", status=502) from exc
    return [h.to_song() for h in hits]


@router.post("/{song_id}/candidates", response_model=CandidatesResponse)
async def song_candidates(
    song_id: str,
    request: Request,
    settings: SettingsDep,
    http: HttpDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    body: CandidatesRequest | None = None,
) -> CandidatesResponse:
    """Browse every source's ranked candidates for a resolved song without starting a job.

    Songsterr matches first (best score first), then Ultimate Guitar Tabs/Chords, then the single
    ``audio`` pseudo-candidate. ``tab_id`` is filled when a job already fetched that candidate.
    Pass a candidate to ``POST /jobs`` as ``candidate`` to fetch exactly it, or list the ones
    already tried in ``exclude``.
    """
    async with session_factory() as session:
        song = await SongRepo(session).get(song_id)
    if song is None:
        raise NotFound(f"song {song_id!r} not found")
    ctx = SourceContext(settings=settings, http=http, session_factory=session_factory, llm=llm)
    return await collect_candidates(
        song,
        request.app.state.sources,
        ctx,
        timeouts=tier_timeouts(settings),
        limit=(body or CandidatesRequest()).limit,
    )
