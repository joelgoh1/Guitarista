"""Noodle mode: the listening pool, the Spotify user grant, and the surprise pick.

The pool is built from the user's own Spotify history only (top tracks, recently played, liked
songs). ``Evidence`` records *why* a track is in the pool; ``PoolEntry.score`` is derived from it
by ``services.listening_pool.score_entry``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from guitarista_api.domain.candidate import Candidate

if TYPE_CHECKING:  # pragma: no cover - typing only
    from guitarista_api.db.models import PoolEntryRow

PoolStatus = Literal["new", "checking", "queued", "ready", "failed", "dismissed"]
Availability = Literal["unknown", "available", "unavailable"]


class Evidence(BaseModel):
    """Where a track showed up in the user's history (ranks are 0-based, best first)."""

    model_config = ConfigDict(extra="ignore")

    top_short: int | None = Field(default=None, description="Rank in top tracks, last 4 weeks")
    top_medium: int | None = Field(default=None, description="Rank in top tracks, last 6 months")
    top_long: int | None = Field(default=None, description="Rank in top tracks, all time")
    recent: int = Field(default=0, ge=0, description="Plays in the recently-played window")
    liked: bool = Field(default=False, description="Present in the user's saved tracks")


class PoolEntry(BaseModel):
    """One candidate song for noodling, as stored in ``listening_pool``."""

    spotify_id: str
    title: str
    artist: str
    album: str | None = None
    artwork_url: str | None = None
    duration_ms: int | None = None
    evidence: Evidence = Field(default_factory=Evidence)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    availability: Availability = "unknown"
    candidate: Candidate | None = Field(
        default=None, description="Songsterr candidate a prefetch job can target directly"
    )
    song_id: str | None = None
    tab_id: str | None = None
    job_id: str | None = None
    status: PoolStatus = "new"
    error: str | None = None
    attempts: int = 0
    refreshed_at: datetime | None = None

    @property
    def spotify_url(self) -> str:
        return f"https://open.spotify.com/track/{self.spotify_id}"

    @classmethod
    def from_row(cls, row: PoolEntryRow) -> PoolEntry:
        return cls(
            spotify_id=row.spotify_id,
            title=row.title,
            artist=row.artist,
            album=row.album,
            artwork_url=row.artwork_url,
            duration_ms=row.duration_ms,
            evidence=Evidence.model_validate(row.evidence or {}),
            score=row.score,
            availability=row.availability,  # type: ignore[arg-type]
            candidate=Candidate.model_validate(row.candidate) if row.candidate else None,
            song_id=row.song_id,
            tab_id=row.tab_id,
            job_id=row.job_id,
            status=row.status,  # type: ignore[arg-type]
            error=row.error,
            attempts=row.attempts,
            refreshed_at=row.refreshed_at,
        )


class SpotifyStatus(BaseModel):
    """Answer to ``GET /spotify/status``."""

    connected: bool = False
    display_name: str | None = None
    spotify_user_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    configured: bool = Field(
        default=False, description="A Spotify client id is set, so login is possible"
    )


class SurprisePick(BaseModel):
    """A single pool entry chosen at random (score-weighted) for the Surprise me button."""

    entry: PoolEntry
    tab_id: str | None = Field(
        default=None, description="Ready tab to open; null means the client should start a job"
    )
    reason: str | None = Field(default=None, description="Human label for why this was picked")
