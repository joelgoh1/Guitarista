"""Build and submit a song→tab job.

Shared by ``POST /jobs`` and the background noodle prefetcher so both go through exactly the
same validation, context wiring and tier chain; the only difference is ``TabRequest.origin``.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.llm import LLMClient
from guitarista_api.adapters.spotify import SpotifyClient
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.errors import UnprocessableError
from guitarista_api.jobs.context import JobContext
from guitarista_api.jobs.manager import JobManager
from guitarista_api.jobs.runner import run_tab_job
from guitarista_api.services.song_resolver import SongResolver
from guitarista_api.services.sources_factory import tier_timeouts
from guitarista_api.services.tier_runner import TierRunner
from guitarista_api.settings import Settings
from guitarista_api.sources.base import TabSource


async def launch_tab_job(
    *,
    body: TabRequest,
    settings: Settings,
    manager: JobManager,
    http: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    spotify: SpotifyClient | None,
    llm: LLMClient | None,
    sources: Sequence[TabSource],
) -> Job:
    """Validate ``body``, create the ``Job`` and start its task. Returns the queued job.

    Raises ``UnprocessableError`` when the request carries neither a song nor audio input.
    """
    if not body.has_song() and not body.has_audio_input():
        raise UnprocessableError(
            "provide song.raw, song.spotify_url, song.title, song_id, upload_id or audio_url"
        )
    job = Job(request=body)
    ctx = JobContext(
        job,
        settings=settings,
        http=http,
        manager=manager,
        session_factory=session_factory,
        llm=llm,
    )
    resolver = SongResolver(session_factory, spotify)
    tier_runner = TierRunner(sources, timeouts=tier_timeouts(settings))
    await manager.submit(
        job,
        lambda: run_tab_job(ctx, manager, body, resolver=resolver, tier_runner=tier_runner),
    )
    return job
