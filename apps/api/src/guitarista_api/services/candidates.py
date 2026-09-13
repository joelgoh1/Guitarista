"""Browse every source's ranked candidates for a resolved song, concurrently, without a job."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.db.repo import TabRepo
from guitarista_api.domain.candidate import Candidate, CandidatesResponse
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song
from guitarista_api.jobs.context import SourceContext
from guitarista_api.sources.base import SourceError, TabSource

log = structlog.get_logger(__name__)

ORDER = {"songsterr": 0, "ultimate_guitar": 1, "audio": 2}


async def collect_candidates(
    song: Song,
    sources: Sequence[TabSource],
    ctx: SourceContext,
    *,
    timeouts: dict[str, float],
    limit: int,
    default_timeout: float = 60.0,
) -> CandidatesResponse:
    warnings: list[str] = []
    probe = TabRequest(song_id=song.id)

    async def one(source: TabSource) -> list[Candidate]:
        if source.name != "audio":
            # Audio reports availability on its pseudo-candidate; the others have nothing to
            # list when disabled or unusable, so they contribute a warning instead.
            ok, reason = source.can_handle(probe, song, ctx)
            if not ok:
                warnings.append(f"{source.name}: {reason or 'not applicable'}")
                return []
        timeout = timeouts.get(source.name, default_timeout)
        try:
            async with asyncio.timeout(timeout):
                found = await source.candidates(song, ctx, limit=limit)
        except TimeoutError:
            warnings.append(f"{source.name}: timed out after {timeout:g}s")
            return []
        except SourceError as exc:
            warnings.append(f"{source.name}: {exc.user_message}")
            return []
        except Exception as exc:
            log.exception("candidates.crashed", source=source.name, song_id=song.id)
            warnings.append(f"{source.name}: {type(exc).__name__}: {exc}")
            return []
        return sorted(found, key=lambda c: -c.score)

    per_source = await asyncio.gather(*(one(s) for s in sources))
    ordered = sorted(
        zip(sources, per_source, strict=True), key=lambda pair: ORDER.get(pair[0].name, 9)
    )
    candidates = [c for _, found in ordered for c in found]
    await fill_tab_ids(candidates, song.id, ctx.session_factory)
    return CandidatesResponse(song_id=song.id, candidates=candidates, warnings=warnings)


async def fill_tab_ids(
    candidates: list[Candidate],
    song_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Point each candidate at the newest already-fetched tab for it (``source_ref`` match)."""
    async with session_factory() as session:
        refs = await TabRepo(session).list_refs_for_song(song_id)
    for candidate in candidates:
        for tab_id, source, source_ref in refs:  # newest first
            if source == candidate.source and matches_ref(candidate, source_ref):
                candidate.tab_id = tab_id
                break


def matches_ref(candidate: Candidate, source_ref: str | None) -> bool:
    if candidate.source == "audio":
        return True  # any audio tab for this song came from the single audio candidate
    if not source_ref:
        return False
    if candidate.source == "songsterr":
        # ``songsterr:<songId>:<revisionId>:<track indices>``
        return source_ref.startswith(f"songsterr:{candidate.external_id}:")
    return source_ref == f"ug:{candidate.external_id}"
