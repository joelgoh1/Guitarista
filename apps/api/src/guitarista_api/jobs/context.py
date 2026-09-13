from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.llm import LLMClient
from guitarista_api.domain.job import Job, TierLogEntry
from guitarista_api.settings import Settings

if TYPE_CHECKING:
    from guitarista_api.jobs.manager import JobManager


class SourceContext:
    """What a tab source needs to search and fetch: config, shared clients, a scratch dir.

    This is the job-less variant used by ``POST /songs/{id}/candidates``; ``log``/``progress``
    are no-ops here and ``JobContext`` overrides them to publish job events. ``llm`` is ``None``
    unless an LLM client is configured; sources must always have a deterministic path and treat
    the LLM as optional.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        http: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient | None = None,
        work_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.session_factory = session_factory
        self.llm = llm
        self.work_dir: Path = work_dir or settings.work_dir

    async def log(self, entry: TierLogEntry) -> None:
        return None

    async def progress(self, value: float, message: str | None = None) -> None:
        return None

    def cancelled(self) -> bool:
        task = asyncio.current_task()
        return task is not None and task.cancelling() > 0

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class JobContext(SourceContext):
    """``SourceContext`` bound to a ``Job``: tier log upserts and progress publish SSE events."""

    def __init__(
        self,
        job: Job,
        *,
        settings: Settings,
        http: httpx.AsyncClient,
        manager: JobManager,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            http=http,
            session_factory=session_factory,
            llm=llm,
            work_dir=settings.work_dir / job.id,
        )
        self.job = job
        self.manager = manager
        self.work_dir.mkdir(parents=True, exist_ok=True)

    async def log(self, entry: TierLogEntry) -> None:
        """Upsert a tier entry by tier name and publish a ``tier`` event."""
        for i, existing in enumerate(self.job.tiers):
            if existing.tier == entry.tier:
                self.job.tiers[i] = entry
                break
        else:
            self.job.tiers.append(entry)
        await self.manager.publish(self.job, "tier", {"tier": entry.model_dump(mode="json")})

    async def progress(self, value: float, message: str | None = None) -> None:
        self.job.progress = max(0.0, min(1.0, value))
        await self.manager.publish(
            self.job, "progress", {"progress": self.job.progress, "message": message}
        )

    def cancelled(self) -> bool:
        return self.manager.is_cancel_requested(self.job.id) or super().cancelled()
