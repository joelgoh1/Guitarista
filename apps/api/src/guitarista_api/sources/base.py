"""Protocol every tab tier implements: ``songsterr``, ``ultimate_guitar``, ``audio``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from guitarista_api.domain.candidate import Candidate
from guitarista_api.domain.enums import TierName
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import Tab

if TYPE_CHECKING:
    from guitarista_api.jobs.context import SourceContext


@dataclass(slots=True)
class SourceResult:
    tab: Tab
    detail: dict[str, Any] = field(default_factory=dict)
    """Structured info for the tier log (candidates, picked, llm_used ...)."""
    message: str | None = None


class SourceError(Exception):
    """A tier failed in an expected way; ``user_message`` is shown in the tier log."""

    def __init__(self, user_message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or {}


def all_excluded_error(total: int, detail: dict[str, Any] | None = None) -> SourceError:
    """Raised when ``request.exclude`` removed every candidate a source had."""
    return SourceError(f"all {total} candidates excluded", detail)


class TabSource(Protocol):
    name: TierName
    deterministic: bool
    """True when the output is reproducible without ML/LLM involvement."""

    def can_handle(
        self, request: TabRequest, song: Song, ctx: SourceContext
    ) -> tuple[bool, str | None]:
        """Cheap pre-check. Returns ``(False, reason)`` to skip the tier without running it."""
        ...

    async def fetch(self, request: TabRequest, song: Song, ctx: SourceContext) -> SourceResult:
        """Produce a tab or raise ``SourceError`` (other exceptions are logged as failures).

        Honours ``request.candidate`` (fetch exactly that id, no ranking) and ``request.exclude``
        (drop those ids from the ranked list before picking).
        """
        ...

    async def candidates(self, song: Song, ctx: SourceContext, *, limit: int) -> list[Candidate]:
        """Search + rank without fetching: what ``fetch`` would consider, best first."""
        ...
