"""Run tab sources in order; first success wins.

Each tier gets a ``TierLogEntry`` with status transitions
``pending -> skipped | running -> success | failed | timeout | cancelled`` published through the
job context so the SSE stream shows the timeline live. Per-tier timeouts come from
``Settings.tier_timeout_<name>``.

``request.candidate`` narrows the run to that one source; ``request.exclude`` is passed down to
every source and the count of excluded ids is recorded in the tier detail.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from guitarista_api.domain.job import TabRequest, TierLogEntry
from guitarista_api.domain.song import Song
from guitarista_api.jobs.context import JobContext
from guitarista_api.sources.base import SourceError, SourceResult, TabSource

log = structlog.get_logger(__name__)


class NoTabFound(Exception):
    def __init__(self, tiers: list[TierLogEntry]) -> None:
        self.tiers = tiers
        super().__init__(self.summary())

    def summary(self) -> str:
        parts = [
            f"{t.tier}: {t.status}" + (f" ({t.message})" if t.message else "") for t in self.tiers
        ]
        return "no tab found. " + "; ".join(parts) if parts else "no tab sources available"


class TierRunner:
    def __init__(
        self,
        sources: Sequence[TabSource],
        *,
        timeouts: dict[str, float] | None = None,
        default_timeout: float = 60.0,
    ) -> None:
        self.sources = list(sources)
        self.timeouts = timeouts or {}
        self.default_timeout = default_timeout

    def timeout_for(self, name: str) -> float:
        return self.timeouts.get(name, self.default_timeout)

    async def run(self, request: TabRequest, song: Song, ctx: JobContext) -> SourceResult:
        sources = self.sources
        if request.candidate is not None:
            sources = [s for s in sources if s.name == request.candidate.source]
        elif request.tiers:
            wanted = set(request.tiers)
            sources = [s for s in sources if s.name in wanted]
        entries: list[TierLogEntry] = []
        total = max(len(sources), 1)
        for i, source in enumerate(sources):
            entry = TierLogEntry(tier=source.name)
            if request.exclude:
                entry.detail["excluded"] = len(request.excluded_ids(source.name))
            entries.append(entry)
            ok, reason = source.can_handle(request, song, ctx)
            if not ok:
                entry.status, entry.message = "skipped", reason or "not applicable"
                await ctx.log(entry)
                continue
            entry.status, entry.started_at = "running", ctx.now()
            entry.message = f"searching {source.name}..."
            await ctx.log(entry)
            await ctx.progress(i / total, f"{source.name}: running")
            try:
                async with asyncio.timeout(self.timeout_for(source.name)):
                    result = await source.fetch(request, song, ctx)
            except TimeoutError:
                entry.status = "timeout"
                entry.message = f"{source.name} timed out after {self.timeout_for(source.name):g}s"
            except asyncio.CancelledError:
                entry.status, entry.message, entry.finished_at = "cancelled", "cancelled", ctx.now()
                await ctx.log(entry)
                raise
            except SourceError as exc:
                entry.status, entry.message = "failed", exc.user_message
                entry.detail = {**entry.detail, **exc.detail}
            except Exception as exc:
                log.exception("tier.crashed", tier=source.name, job_id=getattr(ctx, "job", None))
                entry.status, entry.message = "failed", f"{type(exc).__name__}: {exc}"
            else:
                entry.status = "success"
                entry.message = result.message or f"tab found via {source.name}"
                entry.detail = {
                    **entry.detail,
                    **result.detail,
                    "confidence": result.tab.confidence,
                    "tracks": len(result.tab.tracks),
                    "deterministic": source.deterministic,
                }
                entry.finished_at = ctx.now()
                await ctx.log(entry)
                await ctx.progress((i + 1) / total, f"{source.name}: success")
                return result
            entry.finished_at = ctx.now()
            await ctx.log(entry)
            await ctx.progress((i + 1) / total, f"{source.name}: {entry.status}")
        raise NoTabFound(entries)
