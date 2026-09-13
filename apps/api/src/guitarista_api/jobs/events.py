from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobEventType = Literal["tier", "progress", "done", "error"]


class JobEvent(BaseModel):
    """One SSE frame. ``payload`` always carries a ``job`` snapshot so clients can replace state.

    * ``tier``:     ``{"tier": TierLogEntry, "job": Job}``
    * ``progress``: ``{"progress": float, "message": str | None, "job": Job}``
    * ``done``:     ``{"tab_id": str, "job": Job}``
    * ``error``:    ``{"error": str, "status": JobStatus, "job": Job}``  (failed/cancelled)
    """

    type: JobEventType
    job_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
