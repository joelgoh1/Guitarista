"""The coroutine behind every tab job: resolve song -> run tiers -> save tab -> done."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from guitarista_api.db.repo import TabRepo
from guitarista_api.domain.job import TabRequest, TierLogEntry
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.jobs.context import JobContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.services.song_resolver import SongResolveError, SongResolver
from guitarista_api.services.tier_runner import NoTabFound, TierRunner

log = structlog.get_logger(__name__)


async def run_tab_job(
    ctx: JobContext,
    manager: JobManager,
    request: TabRequest,
    *,
    resolver: SongResolver,
    tier_runner: TierRunner,
) -> None:
    job = ctx.job
    job.status = "running"
    await ctx.progress(0.0, "resolving song")
    started = datetime.now(UTC)
    await ctx.log(TierLogEntry(tier="resolve", status="running", started_at=started))
    try:
        try:
            song = await _resolve(request, resolver)
        except SongResolveError as exc:
            await ctx.log(
                TierLogEntry(
                    tier="resolve",
                    status="failed",
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    message=str(exc),
                )
            )
            raise
        job.song_id = song.id
        label = f"{song.artist} - {song.title}".strip(" -")
        await ctx.log(
            TierLogEntry(
                tier="resolve",
                status="success",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=label,
                detail={
                    "resolved_via": "spotify" if song.spotify_id else "raw",
                    "song_id": song.id,
                },
            )
        )
        await ctx.progress(0.0, f"resolved: {label}")

        result = await tier_runner.run(request, song, ctx)
        tab = result.tab
        tab.song_id = song.id
        async with ctx.session_factory() as session:
            await TabRepo(session).add(tab)

        job.tab_id, job.status, job.progress = tab.id, "done", 1.0
        await manager.publish(job, "done", {"tab_id": tab.id})
        log.info("job.done", job_id=job.id, tab_id=tab.id, source=str(tab.source))
    except asyncio.CancelledError:
        job.status, job.error = "cancelled", "cancelled by user"
        await manager.publish(job, "error", {"error": job.error, "status": job.status})
        raise
    except (SongResolveError, NoTabFound) as exc:
        await _fail(manager, ctx, str(exc))
    except Exception as exc:
        log.exception("job.failed", job_id=job.id)
        await _fail(manager, ctx, f"{type(exc).__name__}: {exc}")


async def _resolve(request: TabRequest, resolver: SongResolver) -> Song:
    if request.song_id:
        return await resolver.by_id(request.song_id)
    if request.song is None or request.song.is_empty():
        if request.upload_id:
            # Audio-only jobs (phase 5) name the song after the upload until metadata exists.
            return await resolver.resolve(SongQuery(raw=f"upload {request.upload_id}"))
        if request.audio_url:
            # The URL is the audio; there is nothing to match it against, so skip verification.
            return await resolver.resolve(SongQuery(raw=request.audio_url))
        raise SongResolveError(
            "job needs a song query (link, text, or title), a song_id, an upload, or an audio_url"
        )
    return await resolver.resolve(request.song)


async def _fail(manager: JobManager, ctx: JobContext, message: str) -> None:
    job = ctx.job
    job.status, job.error = "failed", message
    await manager.publish(job, "error", {"error": message, "status": job.status})
