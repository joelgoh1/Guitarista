from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from uuid import uuid4

from pydantic import BaseModel, Field

from guitarista_api.domain.enums import TabSourceKind


class Duration(BaseModel):
    """Note value as a fraction of a whole note, e.g. num=1, den=4 is a quarter."""

    num: int = 1
    den: int = 4
    dots: int = 0
    tuplet: tuple[int, int] | None = None
    """(actual, normal), e.g. (3, 2) for a triplet."""

    def to_fraction(self) -> Fraction:
        base = Fraction(self.num, self.den)
        total = base
        add = base
        for _ in range(self.dots):
            add /= 2
            total += add
        if self.tuplet:
            actual, normal = self.tuplet
            total = total * normal / actual
        return total


class TimeSignature(BaseModel):
    numerator: int = 4
    denominator: int = 4

    def measure_length(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


class Note(BaseModel):
    string: int = Field(ge=1, description="1 = highest-pitched string")
    fret: int = Field(ge=0, le=30)
    pitch_midi: int | None = None
    tie: bool = False
    dead: bool = False
    ghost: bool = False
    tech: list[str] = Field(default_factory=list)
    finger: int | None = Field(default=None, ge=0, le=4, description="0 thumb, 1 index .. 4 pinky")


class Beat(BaseModel):
    duration: Duration = Field(default_factory=Duration)
    notes: list[Note] = Field(default_factory=list)
    chord_name: str | None = None
    text: str | None = None
    tempo_bpm: float | None = None

    @property
    def is_rest(self) -> bool:
        return not self.notes


class Voice(BaseModel):
    beats: list[Beat] = Field(default_factory=list)


class Measure(BaseModel):
    number: int = Field(ge=1)
    time_signature: TimeSignature | None = None
    voices: list[Voice] = Field(default_factory=lambda: [Voice()])
    marker: str | None = None
    repeat_start: bool = False
    repeat_end: int | None = None


class Track(BaseModel):
    name: str = "Guitar"
    instrument: str = "acoustic_guitar_steel"
    tuning: list[int] = Field(
        default_factory=lambda: [64, 59, 55, 50, 45, 40],
        description="MIDI pitch of open strings, string 1..N (highest first)",
    )
    capo: int = Field(default=0, ge=0)
    measures: list[Measure] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


class Tab(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    song_id: str | None = None
    title: str = "Untitled"
    artist: str | None = None
    source: TabSourceKind = TabSourceKind.MANUAL
    source_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tempo_bpm: float = 120.0
    time_signature: TimeSignature = Field(default_factory=TimeSignature)
    tracks: list[Track] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
