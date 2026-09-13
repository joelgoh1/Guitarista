from __future__ import annotations

from enum import StrEnum
from typing import Literal


class TabSourceKind(StrEnum):
    SONGSTERR = "songsterr"
    ULTIMATE_GUITAR = "ultimate_guitar"
    AUDIO = "audio"
    SCORE = "score"
    MANUAL = "manual"


TierName = Literal["resolve", "songsterr", "ultimate_guitar", "audio"]
CandidateSource = Literal["songsterr", "ultimate_guitar", "audio"]
"""Sources that expose browsable candidates (every tier except the resolve step)."""
TierStatus = Literal["pending", "skipped", "running", "success", "failed", "timeout", "cancelled"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled", "interrupted"]
