from __future__ import annotations

from pydantic import BaseModel, Field


class NoteEvent(BaseModel):
    pitch_midi: int = Field(ge=0, le=127)
    onset_s: float = Field(ge=0.0)
    offset_s: float = Field(ge=0.0)
    velocity: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    string: int | None = Field(
        default=None, ge=1, description="Canonical string (1 = highest) if the model predicts one"
    )
    fret: int | None = Field(default=None, ge=0)

    @property
    def hint(self) -> tuple[int, int] | None:
        return (
            (self.string, self.fret) if self.string is not None and self.fret is not None else None
        )


class TranscriptionResult(BaseModel):
    notes: list[NoteEvent] = Field(default_factory=list)
    tempo_bpm: float | None = None
    beats_s: list[float] = Field(default_factory=list)
    duration_s: float | None = None
    model: str | None = None
    warnings: list[str] = Field(default_factory=list)
