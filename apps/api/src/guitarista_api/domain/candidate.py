"""Browsable tab candidates: what each source *would* pick, exposed before a job runs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from guitarista_api.domain.enums import CandidateSource


class Candidate(BaseModel):
    source: CandidateSource
    external_id: str
    title: str
    artist: str
    score: float = Field(ge=0.0, le=1.0, description="Match score against the resolved song")
    kind: str | None = Field(
        default=None, description='"Tabs" / "Chords" for UG; track-type summary for Songsterr'
    )
    rating: float | None = None
    votes: int | None = None
    track_count: int | None = None
    url: str | None = None
    tab_id: str | None = Field(
        default=None, description="An already fetched tab for this candidate and song, if any"
    )
    available: bool = True
    reason: str | None = Field(default=None, description="Why the candidate is unavailable")


class CandidatesRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="Max candidates per source")


class CandidatesResponse(BaseModel):
    song_id: str
    candidates: list[Candidate]
    warnings: list[str] = Field(
        default_factory=list, description="Sources that failed or were disabled"
    )
