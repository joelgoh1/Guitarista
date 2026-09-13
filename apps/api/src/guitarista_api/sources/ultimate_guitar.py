"""Tier 2: Ultimate Guitar. Search -> filter Tabs/Chords -> rank -> fetch page -> convert.

Ranking is the deterministic rapidfuzz score plus a small rating/votes bonus; Tabs beat Chords on
ties because ASCII tab carries real notes. When the ASCII parse comes up short (intro-only scraps,
odd layouts) and an LLM is configured, the page text is handed to ``ctx.llm.extract_tab_text`` and
the result validated before use. Everything the LLM touches is reported in ``detail.llm_used``.

``candidates()`` stops after ranking; ``fetch()`` honours ``request.candidate`` (fetch exactly
that tab id's page) and ``request.exclude`` (drop those ids before walking the ranked list).
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from guitarista_api.adapters.ultimate_guitar.client import UGClient, UGError
from guitarista_api.adapters.ultimate_guitar.convert import (
    MIN_ASCII_NOTES,
    UGConvertError,
    ascii_to_tab,
    chords_to_tab,
    resolve_tuning,
)
from guitarista_api.adapters.ultimate_guitar.parse import UGResult, UGTabPage
from guitarista_api.domain.candidate import Candidate
from guitarista_api.domain.enums import TierName
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song, SongCandidate
from guitarista_api.domain.tab import Tab
from guitarista_api.domain.validate import validate_tab
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.ranking import CONFIDENT_SCORE, is_ambiguous, rank_candidates
from guitarista_api.sources.base import SourceError, SourceResult, all_excluded_error

log = structlog.get_logger(__name__)

ACCEPTED_TYPES = frozenset({"Tabs", "Chords"})
MAX_PAGE_ATTEMPTS = 3
"""How many ranked candidates to fetch before giving up on the tier."""
RATING_BONUS = 0.03
VOTES_BONUS = 0.04
_TYPE_ORDER = {"Tabs": 0, "Chords": 1}
TAB_BY_ID_URL = "https://tabs.ultimate-guitar.com/tab/{id}"
"""UG redirects the id-only form to the canonical ``/tab/<artist>/<slug>-<id>`` page."""


def popularity_bonus(result: UGResult) -> float:
    """0..0.07 from UG's own rating (0-5) and vote count (log scale, saturates ~10k votes)."""
    rating = (result.rating or 0.0) / 5.0
    votes = min(1.0, math.log10((result.votes or 0) + 1) / 4.0)
    return RATING_BONUS * rating + VOTES_BONUS * votes


class UltimateGuitarSource:
    name: TierName = "ultimate_guitar"
    deterministic = True

    def __init__(self, client: UGClient | None = None) -> None:
        self._client = client

    def _client_for(self, ctx: SourceContext) -> UGClient:
        return self._client or UGClient(ctx.http)

    def can_handle(
        self, request: TabRequest, song: Song, ctx: SourceContext
    ) -> tuple[bool, str | None]:
        if not ctx.settings.enable_ug:
            return False, "Ultimate Guitar tier disabled (GUITARISTA_ENABLE_UG=false)"
        if request.targeted_id(self.name) is not None:
            return True, None
        if not song.title.strip():
            return False, "no title to search for"
        return True, None

    async def candidates(self, song: Song, ctx: SourceContext, *, limit: int) -> list[Candidate]:
        if not ctx.settings.enable_ug:
            return []
        client = self._client_for(ctx)
        detail: dict[str, Any] = {"llm_used": False}
        ranked, by_id = await self._ranked(client, song, ctx, detail)
        out: list[Candidate] = []
        for c in ranked[:limit]:
            result = by_id[_ug_id(c)]
            out.append(
                Candidate(
                    source="ultimate_guitar",
                    external_id=str(result.id),
                    title=result.song_name,
                    artist=result.artist_name,
                    score=c.score,
                    kind=result.type,
                    rating=result.rating,
                    votes=result.votes,
                    url=result.tab_url,
                )
            )
        return out

    async def fetch(self, request: TabRequest, song: Song, ctx: SourceContext) -> SourceResult:
        client = self._client_for(ctx)
        detail: dict[str, Any] = {"llm_used": False}

        targeted = request.targeted_id(self.name)
        if targeted is not None:
            try:
                tab_id = int(targeted)
            except ValueError:
                raise SourceError(f"invalid Ultimate Guitar tab id {targeted!r}", detail) from None
            detail["picked"] = {"id": tab_id, "targeted": True}
            attempts: list[tuple[int, str, UGResult | None]] = [
                (tab_id, TAB_BY_ID_URL.format(id=tab_id), None)
            ]
        else:
            ranked, by_id = await self._ranked(client, song, ctx, detail)
            excluded = request.excluded_ids(self.name)
            kept = [c for c in ranked if str(_ug_id(c)) not in excluded]
            detail["excluded"] = len(ranked) - len(kept)
            if not kept:
                raise all_excluded_error(len(ranked), detail)
            top = kept[0]
            if top.score < CONFIDENT_SCORE:
                names = ", ".join(f"{c.song.artist} - {c.song.title}" for c in kept[:3])
                raise SourceError(
                    f"no confident Ultimate Guitar match (best {top.score:.2f}); closest: {names}",
                    detail,
                )
            attempts = [
                (_ug_id(c), by_id[_ug_id(c)].tab_url, by_id[_ug_id(c)])
                for c in kept[:MAX_PAGE_ATTEMPTS]
            ]

        errors: list[str] = []
        for tab_id, url, result in attempts:
            try:
                page = await client.tab_page(url)
            except UGError as exc:
                kind = result.type if result is not None else "tab"
                errors.append(f"{kind} #{tab_id}: {exc}")
                continue
            detail["picked"] = {
                **detail.get("picked", {}),
                "id": tab_id,
                "type": page.type,
                "url": page.tab_url or url,
                "title": page.song_name,
                "artist": page.artist_name,
                "rating": result.rating if result is not None else None,
                "votes": result.votes if result is not None else None,
            }
            tab = await self._convert(page, song, ctx, detail, errors)
            if tab is not None:
                if request.tuning and request.tuning != tab.tracks[0].tuning:
                    tab.warnings.append("requested tuning ignored; the UG page tuning was kept")
                return SourceResult(
                    tab=tab,
                    detail=detail,
                    message=f"{page.artist_name} - {page.song_name} ({page.type} #{page.id}, "
                    f"{_note_count(tab)} notes)",
                )
        detail["errors"] = errors[:10]
        raise SourceError(
            "Ultimate Guitar pages could not be converted: " + "; ".join(errors[:3]), detail
        )

    # ------------------------------------------------------------------ steps

    async def _ranked(
        self, client: UGClient, song: Song, ctx: SourceContext, detail: dict[str, Any]
    ) -> tuple[list[SongCandidate], dict[int, UGResult]]:
        results, queries = await self._search(client, song, ctx, detail)
        detail["queries"] = queries
        usable = [r for r in results if r.type in ACCEPTED_TYPES]
        detail["results"] = {"total": len(results), "usable": len(usable)}
        if not usable:
            raise SourceError("Ultimate Guitar has no Tabs/Chords results for this song", detail)
        return await self._rank(song, usable, ctx, detail)

    async def _search(
        self, client: UGClient, song: Song, ctx: SourceContext, detail: dict[str, Any]
    ) -> tuple[list[UGResult], list[str]]:
        patterns = [song.normalized_query]
        if song.artist:
            patterns.append(f"{song.artist} {song.title}")
        patterns.append(song.title)
        tried: list[str] = []
        seen: dict[int, UGResult] = {}
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern or pattern in tried:
                continue
            tried.append(pattern)
            if await self._search_into(client, pattern, seen):
                break
        if not seen and ctx.llm is not None:
            rewritten = await ctx.llm.rewrite_query(song, tried)
            if rewritten and rewritten not in tried:
                detail["llm_used"] = True
                detail["rewritten_query"] = rewritten
                tried.append(rewritten)
                await self._search_into(client, rewritten, seen)
        return list(seen.values()), tried

    async def _search_into(self, client: UGClient, pattern: str, seen: dict[int, UGResult]) -> bool:
        try:
            results = await client.search(pattern)
        except SourceError:
            raise
        except UGError as exc:
            log.warning("ug.search_failed", pattern=pattern, error=str(exc))
            return False
        for r in results:
            seen.setdefault(r.id, r)
        return bool(results)

    async def _rank(
        self, song: Song, results: list[UGResult], ctx: SourceContext, detail: dict[str, Any]
    ) -> tuple[list[SongCandidate], dict[int, UGResult]]:
        by_id = {r.id: r for r in results}
        candidates = [
            SongCandidate(
                song=Song(id=f"ug:{r.id}", title=r.song_name, artist=r.artist_name),
                score=0.0,
                source="ultimate_guitar",
            )
            for r in results
        ]
        ranked = rank_candidates(song, candidates)
        boosted = [
            c.model_copy(
                update={"score": round(min(1.0, c.score + popularity_bonus(by_id[_ug_id(c)])), 4)}
            )
            for c in ranked
        ]
        boosted.sort(key=lambda c: (-round(c.score, 2), _TYPE_ORDER.get(by_id[_ug_id(c)].type, 9)))
        if is_ambiguous(boosted) and ctx.llm is not None:
            try:
                reranked = await ctx.llm.rank_candidates(song, boosted[:10])
            except Exception as exc:
                log.warning("ug.llm_rank_failed", error=str(exc))
                reranked = None
            if reranked and ctx.llm.last_error is None:
                # Dedupe on song id: the LLM rescored copies would not compare equal.
                seen = {c.song.id for c in reranked}
                boosted = reranked + [c for c in boosted if c.song.id not in seen]
                detail["llm_used"] = True
        detail["candidates"] = [
            {
                "id": _ug_id(c),
                "type": by_id[_ug_id(c)].type,
                "title": c.song.title,
                "artist": c.song.artist,
                "score": c.score,
                "rating": by_id[_ug_id(c)].rating,
                "votes": by_id[_ug_id(c)].votes,
            }
            for c in boosted[:5]
        ]
        return boosted, by_id

    async def _convert(
        self,
        page: UGTabPage,
        song: Song,
        ctx: SourceContext,
        detail: dict[str, Any],
        errors: list[str],
    ) -> Tab | None:
        if page.is_chords:
            try:
                return chords_to_tab(page, song)
            except UGConvertError as exc:
                errors.append(f"Chords #{page.id}: {exc}")
                return None
        try:
            tab = ascii_to_tab(page, song)
        except UGConvertError as exc:
            errors.append(f"Tabs #{page.id}: {exc}")
            tab = None
        if tab is not None and _note_count(tab) >= MIN_ASCII_NOTES:
            return tab
        if ctx.llm is None:
            errors.append(f"Tabs #{page.id}: no LLM configured to recover the tab text")
            return None
        detail["llm_used"] = True
        tuning = resolve_tuning(page, [])
        extracted = await ctx.llm.extract_tab_text(page.content, tuning)
        if extracted is None:
            errors.append(f"Tabs #{page.id}: LLM extraction declined ({ctx.llm.last_error})")
            return tab
        problems = validate_tab(extracted)
        if problems or _note_count(extracted) < MIN_ASCII_NOTES:
            errors.append(f"Tabs #{page.id}: LLM tab rejected ({problems[:2] or 'too few notes'})")
            return tab
        extracted.title = extracted.title if extracted.title != "Untitled" else page.song_name
        extracted.artist = extracted.artist or page.artist_name or None
        extracted.song_id = song.id
        extracted.source = "ultimate_guitar"  # type: ignore[assignment]
        extracted.source_ref = f"ug:{page.id}"
        if page.capo and extracted.tracks and not extracted.tracks[0].capo:
            extracted.tracks[0].capo = page.capo
        detail["llm_extracted"] = True
        return extracted


def _ug_id(candidate: SongCandidate) -> int:
    return int(candidate.song.id.split(":")[1])


def _note_count(tab: Tab) -> int:
    return sum(
        len(beat.notes)
        for track in tab.tracks
        for measure in track.measures
        for voice in measure.voices
        for beat in voice.beats
    )
