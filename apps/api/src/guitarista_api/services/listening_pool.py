"""Build the noodle listening pool from the user's own Spotify history.

Three steps, all driven by :func:`build_pool`:

1. fetch top tracks (short/medium/long), recently played and saved tracks concurrently;
2. merge them by ``spotify_id`` accumulating :class:`~guitarista_api.domain.noodle.Evidence`
   and deriving a 0..1 ``score`` with the pure :func:`score_entry`;
3. decide what is playable: an entry whose song already has a tab in the library is ``ready``
   straight away, and the best unknown entries get one cheap Songsterr availability probe.

Everything that touches the network is best-effort: a failing Spotify endpoint (or a Songsterr
hiccup) degrades the pool, it never sinks the refresh.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.spotify import SpotifyTrack
from guitarista_api.adapters.spotify_user import SpotifyUserClient
from guitarista_api.db.repo import SongRepo, TabRepo
from guitarista_api.db.repos_noodle import PoolRepo
from guitarista_api.domain.noodle import Evidence, PoolEntry
from guitarista_api.domain.song import Song
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.normalize import normalize_title
from guitarista_api.services.ranking import CONFIDENT_SCORE
from guitarista_api.settings import Settings
from guitarista_api.sources.base import TabSource
from guitarista_api.sources.songsterr import SongsterrSource

log = structlog.get_logger(__name__)

TOP_RANK_DEPTH = 50
"""Spotify returns at most 50 top tracks per range; ranks are scaled against that."""

RECENT_CAP = 5
"""Plays beyond this in the recently-played window stop adding to the score."""

AVAILABILITY_BATCH = 20
"""How many still-unknown entries get a Songsterr probe per refresh."""

AVAILABILITY_CONCURRENCY = 3

#: Weight of each evidence channel (see the plan); the sum is clamped to 1.0.
W_TOP_SHORT = 1.0
W_TOP_MEDIUM = 0.7
W_TOP_LONG = 0.4
W_RECENT = 0.5
W_LIKED = 0.25


class PoolSummary(BaseModel):
    """What one :func:`build_pool` run did."""

    fetched: int = Field(default=0, description="Distinct tracks seen across all endpoints")
    new: int = Field(default=0, description="Entries that were not in the pool before")
    available: int = Field(default=0, description="Entries confirmed playable this run")
    ready: int = Field(default=0, description="Entries that already have a tab in the library")
    skipped: bool = Field(default=False, description="Pool was still fresh, nothing was fetched")
    errors: list[str] = Field(default_factory=list, description="Endpoints that failed")


# --------------------------------------------------------------------------- pure


def score_entry(evidence: Evidence) -> float:
    """0..1 desirability of a track, from where it showed up in the history (pure)."""
    score = 0.0
    for rank, weight in (
        (evidence.top_short, W_TOP_SHORT),
        (evidence.top_medium, W_TOP_MEDIUM),
        (evidence.top_long, W_TOP_LONG),
    ):
        if rank is not None:
            score += weight * max(0.0, 1.0 - rank / TOP_RANK_DEPTH)
    if evidence.recent:
        score += W_RECENT * min(evidence.recent, RECENT_CAP) / RECENT_CAP
    if evidence.liked:
        score += W_LIKED
    return min(1.0, round(score, 6))


def merge_tracks(
    *,
    top_short: Sequence[SpotifyTrack] = (),
    top_medium: Sequence[SpotifyTrack] = (),
    top_long: Sequence[SpotifyTrack] = (),
    recent: Sequence[SpotifyTrack] = (),
    saved: Sequence[SpotifyTrack] = (),
) -> list[PoolEntry]:
    """Fold the five history feeds into scored pool entries, best first (pure).

    ``recent`` may legitimately contain the same track several times: those are repeat plays and
    each one counts. The other feeds are deduped by id.
    """
    entries: dict[str, PoolEntry] = {}

    def entry_for(track: SpotifyTrack) -> PoolEntry:
        existing = entries.get(track.id)
        if existing is not None:
            return existing
        made = PoolEntry(
            spotify_id=track.id,
            title=track.name,
            artist=", ".join(track.artists),
            album=track.album,
            artwork_url=track.artwork_url,
            duration_ms=track.duration_ms,
        )
        entries[track.id] = made
        return made

    for feed, field in (
        (top_short, "top_short"),
        (top_medium, "top_medium"),
        (top_long, "top_long"),
    ):
        for rank, track in enumerate(feed):
            evidence = entry_for(track).evidence
            if getattr(evidence, field) is None:
                setattr(evidence, field, rank)
    for track in recent:
        entry_for(track).evidence.recent += 1
    for track in saved:
        entry_for(track).evidence.liked = True

    for entry in entries.values():
        entry.score = score_entry(entry.evidence)
    return sorted(entries.values(), key=lambda e: (-e.score, e.spotify_id))


def entry_song(entry: PoolEntry) -> Song:
    """The :class:`Song` a source should search for when probing this entry."""
    return Song(
        id=f"spotify_{entry.spotify_id}",
        title=normalize_title(entry.title),
        artist=entry.artist,
        album=entry.album,
        duration_s=entry.duration_ms / 1000 if entry.duration_ms else None,
        spotify_id=entry.spotify_id,
        artwork_url=entry.artwork_url,
    )


# --------------------------------------------------------------------------- build


async def build_pool(
    *,
    client: SpotifyUserClient,
    session_factory: async_sessionmaker[AsyncSession],
    sources: Sequence[TabSource],
    settings: Settings,
    force: bool = False,
) -> PoolSummary:
    """Refresh the listening pool. Returns a summary; never raises for a partial fetch."""
    if not force and await _is_fresh(session_factory, settings.noodle_refresh_hours):
        return PoolSummary(skipped=True)

    feeds, errors = await _fetch_history(client)
    entries = merge_tracks(**feeds)
    summary = PoolSummary(fetched=len(entries), errors=errors)
    if not entries:
        return summary

    async with session_factory() as session:
        known = {e.spotify_id for e in await PoolRepo(session).list(limit=10_000)}
        summary.ready = await _attach_known_tabs(session, entries)
        summary.new = len([e for e in entries if e.spotify_id not in known])
        await PoolRepo(session).upsert_many(entries)

    summary.available = await _probe_availability(
        session_factory=session_factory, sources=sources, settings=settings, client=client
    )
    log.info(
        "noodle.pool_built",
        fetched=summary.fetched,
        new=summary.new,
        ready=summary.ready,
        available=summary.available,
    )
    return summary


async def _is_fresh(
    session_factory: async_sessionmaker[AsyncSession], refresh_hours: float
) -> bool:
    async with session_factory() as session:
        newest = await PoolRepo(session).newest_refresh()
    if newest is None:
        return False
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    return datetime.now(UTC) - newest < timedelta(hours=refresh_hours)


async def _fetch_history(
    client: SpotifyUserClient,
) -> tuple[dict[str, list[SpotifyTrack]], list[str]]:
    """All five feeds concurrently; a failing endpoint yields an empty list plus an error note."""
    names = ("top_short", "top_medium", "top_long", "recent", "saved")
    results = await asyncio.gather(
        client.top_tracks("short_term"),
        client.top_tracks("medium_term"),
        client.top_tracks("long_term"),
        client.recently_played(),
        client.saved_tracks(),
        return_exceptions=True,
    )
    feeds: dict[str, list[SpotifyTrack]] = {}
    errors: list[str] = []
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("noodle.history_feed_failed", feed=name, error=str(result))
            errors.append(f"{name}: {result}")
            feeds[name] = []
        else:
            feeds[name] = list(result)
    return feeds, errors


async def _attach_known_tabs(session: AsyncSession, entries: Sequence[PoolEntry]) -> int:
    """Mark entries whose song already has a tab as ``ready`` (in place). Returns the count."""
    songs, tabs = SongRepo(session), TabRepo(session)
    ready = 0
    for entry in entries:
        song = await songs.find_match(
            spotify_id=entry.spotify_id,
            normalized_query=entry_song(entry).normalized_query,
        )
        if song is None:
            continue
        entry.song_id = song.id
        refs = await tabs.list_refs_for_song(song.id)
        if not refs:
            continue
        entry.tab_id = refs[0][0]
        entry.status = "ready"
        entry.availability = "available"
        ready += 1
    return ready


async def _probe_availability(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    sources: Sequence[TabSource],
    settings: Settings,
    client: SpotifyUserClient,
) -> int:
    """One Songsterr search per still-unknown entry, three at a time."""
    songsterr = next((s for s in sources if isinstance(s, SongsterrSource)), None)
    if songsterr is None or not settings.enable_songsterr:
        return 0
    async with session_factory() as session:
        candidates = [
            e
            for e in await PoolRepo(session).list(statuses=["new", "checking"], limit=200)
            if e.availability == "unknown"
        ][:AVAILABILITY_BATCH]
    if not candidates:
        return 0

    ctx = SourceContext(
        settings=settings, http=client.http, session_factory=session_factory, llm=None
    )
    sem = asyncio.Semaphore(AVAILABILITY_CONCURRENCY)

    async def probe(entry: PoolEntry) -> bool:
        async with sem:
            try:
                found = await songsterr.candidates(entry_song(entry), ctx, limit=1)
            except Exception as exc:  # transient: leave it unknown so the next run retries
                log.warning("noodle.probe_failed", spotify_id=entry.spotify_id, error=str(exc))
                return False
        top = found[0] if found else None
        available = top is not None and top.score >= CONFIDENT_SCORE
        async with session_factory() as session:
            await PoolRepo(session).set_status(
                entry.spotify_id,
                "new",
                availability="available" if available else "unavailable",
                candidate_json=top.model_dump(mode="json") if available and top else None,
            )
        return available

    return sum(await asyncio.gather(*(probe(e) for e in candidates)))
