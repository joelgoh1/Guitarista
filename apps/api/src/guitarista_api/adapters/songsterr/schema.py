"""Lenient Pydantic models for the Songsterr JSON payloads.

Shapes were recorded from the live API on 2026-09-11 (see ``tests/fixtures/songsterr/README.md``).
Everything is ``extra="ignore"`` and optional-by-default because the API is unofficial and drifts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SearchTrack(_Lenient):
    instrumentId: int | None = None
    instrument: str | None = None
    name: str | None = None
    tuning: list[int] | None = None
    views: int | None = None
    difficulty: int | None = None
    hash: str | None = None


class SearchResult(_Lenient):
    songId: int
    artistId: int | None = None
    artist: str = ""
    title: str = ""
    hasChords: bool = False
    hasPlayer: bool = False
    tracks: list[SearchTrack] = Field(default_factory=list)


class MetaTrack(_Lenient):
    instrumentId: int = 0
    instrument: str = ""
    name: str = ""
    tuning: list[int] = Field(default_factory=list)
    hash: str | None = None
    views: int | None = None
    difficulty: int | None = None
    isVocalTrack: bool = False
    isEmpty: bool = False


class Meta(_Lenient):
    songId: int
    revisionId: int
    image: str
    title: str = ""
    artist: str = ""
    tracks: list[MetaTrack] = Field(default_factory=list)
    defaultTrack: int | None = None
    popularTrack: int | None = None
    popularTrackGuitar: int | None = None
    popularTrackBass: int | None = None
    popularTrackDrum: int | None = None
    popularTrackVocals: int | None = None


class TempoAutomation(_Lenient):
    bpm: float
    measure: int = 0
    position: int = 0
    type: int | None = None


class Automations(_Lenient):
    tempo: list[TempoAutomation] = Field(default_factory=list)


class TrackNote(_Lenient):
    string: int | None = None
    fret: int | None = None
    rest: bool = False
    tie: bool = False
    dead: bool = False
    ghost: bool = False
    hp: bool = False
    slide: Any = None
    bend: Any = None
    vibrato: bool = False
    palmMute: bool = False
    harmonic: Any = None
    letRing: bool = False
    staccato: bool = False
    accentuated: Any = None
    tremolo: Any = None
    tapping: bool = False


class ChordText(_Lenient):
    text: str = ""


class TrackBeat(_Lenient):
    notes: list[TrackNote] = Field(default_factory=list)
    type: int | None = None
    duration: list[int] = Field(default_factory=lambda: [1, 4])
    rest: bool = False
    dotted: bool = False
    dots: int = 0
    tuplet: int | None = None
    letRing: bool = False
    palmMute: bool = False
    chord: ChordText | None = None
    text: str | None = None
    velocity: str | None = None
    tempo: float | None = None
    upStroke: bool = False
    downStroke: bool = False


class TrackVoice(_Lenient):
    beats: list[TrackBeat] = Field(default_factory=list)
    rest: bool = False


class Marker(_Lenient):
    text: str = ""


class TrackMeasure(_Lenient):
    signature: list[int] | None = None
    marker: Marker | None = None
    voices: list[TrackVoice] = Field(default_factory=list)
    rest: bool = False
    repeatStart: bool = False
    repeat: int | None = None
    doubleBarline: bool = False


class TrackJson(_Lenient):
    name: str = ""
    capo: int = 0
    frets: int | None = None
    tuning: list[int] = Field(default_factory=lambda: [64, 59, 55, 50, 45, 40])
    strings: int | None = None
    instrumentId: int = 0
    instrument: str = ""
    automations: Automations = Field(default_factory=Automations)
    measures: list[TrackMeasure] = Field(default_factory=list)
    songId: int | None = None
    revisionId: int | None = None
    partId: int | None = None
