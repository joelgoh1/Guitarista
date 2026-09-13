from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from guitarista_api.domain.enums import CandidateSource, JobStatus, TierName, TierStatus
from guitarista_api.domain.song import SongQuery
from guitarista_api.solver.cost import CostProfile

_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class CandidateRef(BaseModel):
    """Points at one browsable candidate: a Songsterr ``songId``, a UG tab id, or ``"audio"``."""

    source: CandidateSource
    external_id: str = Field(min_length=1)


class TabRequest(BaseModel):
    """Body of ``POST /jobs``: ``song`` (link / text / title+artist), ``song_id`` (an already
    resolved song) and/or ``upload_id``. ``candidate`` fetches exactly one browsed candidate;
    ``exclude`` makes every tier skip the listed candidates before picking ("not this one, next").
    ``origin`` marks background "noodle" prefetch jobs (from the Spotify listening pool) so the
    UI can tell them apart from jobs the user asked for explicitly.
    """

    song: SongQuery | None = None
    song_id: str | None = Field(
        default=None, description="Reuse an already resolved song (from /songs/resolve or a job)"
    )
    upload_id: str | None = None
    audio_url: str | None = Field(
        default=None,
        description=(
            "Exact media URL for the audio tier to download with yt-dlp, instead of searching. "
            "Ignored when upload_id is set; still requires GUITARISTA_ENABLE_YTDLP."
        ),
    )
    candidate: CandidateRef | None = Field(
        default=None,
        description="Fetch exactly this candidate; only its source runs and nothing is ranked",
    )
    exclude: list[CandidateRef] = Field(
        default_factory=list, description="Candidates every tier must skip before picking"
    )
    tuning: list[int] | None = None
    capo: int = Field(default=0, ge=0, le=12)
    max_fret: int | None = Field(
        default=None, ge=1, le=24, description="Highest fret the solver may use (audio tier)"
    )
    cost_profile: CostProfile = Field(
        default="tabgen",
        description=(
            "Fretting preference for the solver (audio tier): 'tabgen' classic heuristics, "
            "'lead' stays in position instead of jumping to open strings, 'beginner' favours "
            "open strings and low frets"
        ),
    )
    tiers: list[TierName] | None = Field(
        default=None, description="Restrict to these tiers (default: all enabled, in order)"
    )
    origin: Literal["user", "noodle"] = Field(
        default="user",
        description=(
            "Who asked for this job: 'user' for an explicit request, 'noodle' for a background "
            "prefetch job started from the Spotify listening pool, so the UI can tell them apart"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_query_key(cls, data: Any) -> Any:
        if isinstance(data, dict) and "song" not in data and "query" in data:
            data = {**data, "song": data.pop("query")}
        return data

    @field_validator("audio_url")
    @classmethod
    def _http_url_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not _HTTP_URL_RE.match(value):
            raise ValueError("audio_url must be an http(s) URL")
        return value

    def has_audio_input(self) -> bool:
        """True when the request carries audio the tier can work from without searching."""
        return bool(self.upload_id) or bool(self.audio_url)

    def has_song(self) -> bool:
        return bool(self.song_id) or (self.song is not None and not self.song.is_empty())

    def excluded_ids(self, source: str) -> set[str]:
        return {ref.external_id for ref in self.exclude if ref.source == source}

    def targeted_id(self, source: str) -> str | None:
        """The external id to fetch when ``candidate`` points at ``source``, else ``None``."""
        if self.candidate is not None and self.candidate.source == source:
            return self.candidate.external_id
        return None


class TierLogEntry(BaseModel):
    tier: TierName
    status: TierStatus = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = "queued"
    request: TabRequest
    song_id: str | None = None
    tab_id: str | None = None
    tiers: list[TierLogEntry] = Field(default_factory=list)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
