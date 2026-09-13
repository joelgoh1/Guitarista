"""Tier 1: Songsterr. Search -> rank -> meta -> fetch all eligible tracks -> convert.

``candidates()`` stops after ranking; ``fetch()`` honours ``request.candidate`` (go straight to
that ``songId``) and ``request.exclude`` (drop those ``songId``s before picking the top one).
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any

import structlog

from guitarista_api.adapters.songsterr.client import SongsterrClient, SongsterrError
from guitarista_api.adapters.songsterr.convert import (
    ConversionError,
    eligible_track_indices,
    songsterr_to_tab,
)
from guitarista_api.adapters.songsterr.schema import Meta, SearchResult, TrackJson
from guitarista_api.domain.candidate import Candidate
from guitarista_api.domain.enums import TierName
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song, SongCandidate
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.ranking import CONFIDENT_SCORE, is_ambiguous, rank_candidates
from guitarista_api.sources.base import SourceError, SourceResult, all_excluded_error

log = structlog.get_logger(__name__)

MAX_CONCURRENT_TRACKS = 8
SONG_URL = "https://www.songsterr.com/a/wsa/{slug}-tab-s{song_id}"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def song_url(result: SearchResult) -> str:
    slug = _SLUG_RE.sub("-", f"{result.artist} {result.title}".lower()).strip("-") or "song"
    return SONG_URL.format(slug=slug, song_id=result.songId)


def track_summary(result: SearchResult) -> str | None:
    """``"guitar x4, bass, vocals x2"`` from the search result's track list."""
    kinds: Counter[str] = Counter()
    for track in result.tracks:
        kind = (track.hash or "").split("_", 1)[0] or (track.instrument or "other").lower()
        kinds[kind] += 1
    if not kinds:
        return None
    return ", ".join(f"{k} x{n}" if n > 1 else k for k, n in kinds.most_common())


class SongsterrSource:
    name: TierName = "songsterr"
    deterministic = True

    def __init__(self, client: SongsterrClient | None = None) -> None:
        self._client = client

    def _client_for(self, ctx: SourceContext) -> SongsterrClient:
        return self._client or SongsterrClient(ctx.http)

    def can_handle(
        self, request: TabRequest, song: Song, ctx: SourceContext
    ) -> tuple[bool, str | None]:
        if not ctx.settings.enable_songsterr:
            return False, "Songsterr tier disabled (GUITARISTA_ENABLE_SONGSTERR=false)"
        if request.targeted_id(self.name) is not None:
            return True, None
        if not song.title.strip():
            return False, "no title to search for"
        return True, None

    async def candidates(self, song: Song, ctx: SourceContext, *, limit: int) -> list[Candidate]:
        if not ctx.settings.enable_songsterr:
            return []
        client = self._client_for(ctx)
        detail: dict[str, Any] = {"llm_used": False}
        ranked, by_id = await self._ranked(client, song, ctx, detail)
        return [
            Candidate(
                source="songsterr",
                external_id=str(_song_id(c)),
                title=c.song.title,
                artist=c.song.artist,
                score=c.score,
                kind=track_summary(by_id[_song_id(c)]),
                track_count=len(by_id[_song_id(c)].tracks),
                url=song_url(by_id[_song_id(c)]),
            )
            for c in ranked[:limit]
        ]

    async def fetch(self, request: TabRequest, song: Song, ctx: SourceContext) -> SourceResult:
        client = self._client_for(ctx)
        detail: dict[str, Any] = {"llm_used": False}

        targeted = request.targeted_id(self.name)
        if targeted is not None:
            try:
                song_id = int(targeted)
            except ValueError:
                raise SourceError(f"invalid Songsterr songId {targeted!r}", detail) from None
            detail["picked"] = {"songId": song_id, "targeted": True}
        else:
            ranked, _ = await self._ranked(client, song, ctx, detail)
            excluded = request.excluded_ids(self.name)
            kept = [c for c in ranked if str(_song_id(c)) not in excluded]
            detail["excluded"] = len(ranked) - len(kept)
            if not kept:
                raise all_excluded_error(len(ranked), detail)
            top = kept[0]
            if top.score < CONFIDENT_SCORE:
                names = ", ".join(f"{c.song.artist} - {c.song.title}" for c in kept[:3])
                raise SourceError(
                    f"no confident Songsterr match (best {top.score:.2f}); closest: {names}",
                    detail,
                )
            song_id = _song_id(top)
            detail["picked"] = {
                "songId": song_id,
                "title": top.song.title,
                "artist": top.song.artist,
            }
        return await self._fetch_song(client, song_id, song, detail)

    # ------------------------------------------------------------------ steps

    async def _ranked(
        self, client: SongsterrClient, song: Song, ctx: SourceContext, detail: dict[str, Any]
    ) -> tuple[list[SongCandidate], dict[int, SearchResult]]:
        results, queries = await self._search(client, song)
        if not results and ctx.llm is not None:
            # One LLM-rewritten retry (typos, "official video" noise) before giving up.
            rewritten = await ctx.llm.rewrite_query(song, queries)
            if rewritten and rewritten not in queries:
                detail["llm_used"], detail["rewritten_query"] = True, rewritten
                queries.append(rewritten)
                try:
                    results = await client.search(rewritten)
                except SongsterrError as exc:
                    log.warning("songsterr.search_failed", pattern=rewritten, error=str(exc))
        detail["queries"] = queries
        if not results:
            raise SourceError("Songsterr has no results for this song", detail)
        ranked = await self._rank(song, results, ctx, detail)
        return ranked, {r.songId: r for r in results}

    async def _fetch_song(
        self, client: SongsterrClient, song_id: int, song: Song, detail: dict[str, Any]
    ) -> SourceResult:
        try:
            meta = await client.meta(song_id)
        except SongsterrError as exc:
            raise SourceError(f"Songsterr meta lookup failed: {exc}", detail) from exc
        picked = detail.setdefault("picked", {"songId": song_id})
        picked.setdefault("title", meta.title)
        picked.setdefault("artist", meta.artist)
        indices = eligible_track_indices(meta)
        if not indices:
            raise SourceError("Songsterr song has no importable (non-vocal) tracks", detail)
        detail["revisionId"] = meta.revisionId

        tracks, skipped = await self._fetch_tracks(client, meta, indices)
        detail["tracks"] = [i for i, _ in tracks]
        if skipped:
            detail["skipped_tracks"] = skipped
        if not tracks:
            raise SourceError("could not download any Songsterr track", detail)

        try:
            tab = songsterr_to_tab(meta, tracks, song)
        except ConversionError as exc:
            detail["errors"] = exc.errors[:10]
            raise SourceError(f"Songsterr tab conversion failed: {exc}", detail) from exc
        if skipped:
            tab.warnings.append(f"{len(skipped)} track(s) could not be downloaded: {skipped}")
        return SourceResult(
            tab=tab,
            detail=detail,
            message=f"{meta.artist} - {meta.title} ({len(tracks)} tracks, rev {meta.revisionId})",
        )

    async def _search(
        self, client: SongsterrClient, song: Song
    ) -> tuple[list[SearchResult], list[str]]:
        patterns = [song.normalized_query]
        if song.artist:
            patterns.append(f"{song.artist} {song.title}")
        patterns.append(song.title)
        tried: list[str] = []
        seen: dict[int, SearchResult] = {}
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern or pattern in tried:
                continue
            tried.append(pattern)
            try:
                results = await client.search(pattern)
            except SongsterrError as exc:
                log.warning("songsterr.search_failed", pattern=pattern, error=str(exc))
                continue
            for r in results:
                seen.setdefault(r.songId, r)
            if results:
                break
        return list(seen.values()), tried

    async def _rank(
        self, song: Song, results: list[SearchResult], ctx: SourceContext, detail: dict[str, Any]
    ) -> list[SongCandidate]:
        candidates = [
            SongCandidate(
                song=Song(id=f"songsterr:{r.songId}", title=r.title, artist=r.artist),
                score=0.0,
                source="songsterr",
            )
            for r in results
        ]
        ranked = rank_candidates(song, candidates)
        if is_ambiguous(ranked) and ctx.llm is not None:
            # Optional LLM re-rank; deterministic order is kept if it declines or fails.
            try:
                reranked = await ctx.llm.rank_candidates(song, ranked[:10])
            except Exception as exc:
                log.warning("songsterr.llm_rank_failed", error=str(exc))
                reranked = None
            if reranked and ctx.llm.last_error is None:
                # Dedupe on song id: the LLM rescored copies would not compare equal.
                seen = {c.song.id for c in reranked}
                ranked = reranked + [c for c in ranked if c.song.id not in seen]
                detail["llm_used"] = True
        detail["candidates"] = [
            {
                "songId": c.song.id.split(":")[1],
                "title": c.song.title,
                "artist": c.song.artist,
                "score": c.score,
            }
            for c in ranked[:5]
        ]
        return ranked

    async def _fetch_tracks(
        self, client: SongsterrClient, meta: Meta, indices: list[int]
    ) -> tuple[list[tuple[int, TrackJson]], list[int]]:
        sem = asyncio.Semaphore(MAX_CONCURRENT_TRACKS)

        async def one(idx: int) -> TrackJson | None:
            async with sem:
                try:
                    return await client.track(meta.songId, meta.revisionId, meta.image, idx)
                except SongsterrError as exc:
                    log.warning("songsterr.track_failed", track=idx, error=str(exc))
                    return None

        fetched = await asyncio.gather(*(one(i) for i in indices))
        tracks = [(i, t) for i, t in zip(indices, fetched, strict=True) if t is not None]
        skipped = [i for i, t in zip(indices, fetched, strict=True) if t is None]
        return tracks, skipped


def _song_id(candidate: SongCandidate) -> int:
    return int(candidate.song.id.split(":")[1])
