from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SongQuery(BaseModel):
    """What the user typed or pasted; at least one of the fields is expected."""

    raw: str | None = None
    spotify_url: str | None = None
    title: str | None = None
    artist: str | None = None

    def is_empty(self) -> bool:
        return not any(v and v.strip() for v in (self.raw, self.spotify_url, self.title))


class Song(BaseModel):
    id: str
    title: str
    artist: str
    album: str | None = None
    duration_s: float | None = None
    spotify_id: str | None = None
    isrc: str | None = None
    artwork_url: str | None = None
    normalized_query: str = Field(
        default="", description="Normalized '<artist> <title>' used for search and dedupe"
    )

    @model_validator(mode="after")
    def _fill_normalized_query(self) -> Song:
        if not self.normalized_query:
            from guitarista_api.services.normalize import normalized_query

            self.normalized_query = normalized_query(self.title, self.artist)
        return self


class SongCandidate(BaseModel):
    song: Song
    score: float = Field(ge=0.0, le=1.0)
    source: str
