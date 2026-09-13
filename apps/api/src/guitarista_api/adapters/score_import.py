from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import structlog
from music21 import chord as m21chord
from music21 import converter, meter, note, stream, tempo
from pydantic import BaseModel, Field

from guitarista_api.domain.tab import TimeSignature
from guitarista_api.solver.model import ChordEvent

log = structlog.get_logger(__name__)

#: Formats music21 reads directly.
SUPPORTED_SUFFIXES = {".musicxml", ".xml", ".mxl", ".mid", ".midi"}

#: Formats that need a MuseScore round-trip to MusicXML first (see adapters/musescore.py).
MUSESCORE_SUFFIXES = {".mscz", ".mscx", ".gp", ".gpx", ".gp3", ".gp4", ".gp5", ".cap", ".capx"}

ALL_SCORE_SUFFIXES = SUPPORTED_SUFFIXES | MUSESCORE_SUFFIXES


class ScorePart(BaseModel):
    index: int
    name: str
    note_count: int
    pitch_range: tuple[int, int] | None = None


class ScoreInfo(BaseModel):
    title: str | None = None
    artist: str | None = None
    parts: list[ScorePart] = Field(default_factory=list)


class ScoreMeta(BaseModel):
    tempo_bpm: float = 120.0
    time_signature: TimeSignature = Field(default_factory=TimeSignature)
    title: str | None = None
    artist: str | None = None


class UnsupportedScore(ValueError):
    pass


def _load(path: Path) -> stream.Score:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise UnsupportedScore(f"unsupported score type {path.suffix!r}")
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        parsed = converter.parse(str(path))
    except Exception as exc:  # music21 raises many exception types
        raise UnsupportedScore(f"could not parse score: {exc}") from exc
    if isinstance(parsed, stream.Score):
        return parsed
    score = stream.Score()
    score.insert(0, parsed)
    return score


def _parts(score: stream.Score) -> list[stream.Part]:
    parts = list(score.parts)
    return parts or [stream.Part(score.flatten().notesAndRests)]


def parse_score(path: Path) -> ScoreInfo:
    score = _load(path)
    title, artist = _metadata(score)
    infos: list[ScorePart] = []
    for i, part in enumerate(_parts(score)):
        pitches = [p.midi for el in part.flatten().notes for p in el.pitches]
        infos.append(
            ScorePart(
                index=i,
                name=part.partName or f"Part {i + 1}",
                note_count=len(pitches),
                pitch_range=(min(pitches), max(pitches)) if pitches else None,
            )
        )
    return ScoreInfo(title=title, artist=artist, parts=infos)


def _metadata(score: stream.Score) -> tuple[str | None, str | None]:
    md = score.metadata
    if md is None:
        return None, None
    title = md.title if md.title and md.title != "Untitled score" else None
    composer = md.composer if md.composer and md.composer != "Composer / arranger" else None
    return title, composer


def score_to_chord_events(
    path: Path, part_index: int = 0, *, trim_trailing_rests: bool = True
) -> tuple[list[ChordEvent], ScoreMeta]:
    """Flatten one part into chord events (rests included), merging tied notes.

    ``trim_trailing_rests`` drops rest-only events at the very end (notation software often
    pads scores with empty measures).
    """
    score = _load(path)
    parts = _parts(score)
    if not 0 <= part_index < len(parts):
        raise UnsupportedScore(f"part_index {part_index} out of range (0..{len(parts) - 1})")
    part = parts[part_index]
    flat = part.flatten()
    title, artist = _metadata(score)
    meta = ScoreMeta(
        tempo_bpm=_tempo(flat, score),
        time_signature=_time_signature(flat),
        title=title,
        artist=artist,
    )
    events = _events(flat)
    if trim_trailing_rests:
        while events and events[-1].is_rest:
            events.pop()
    log.debug("score.imported", path=str(path), events=len(events), tempo=meta.tempo_bpm)
    return events, meta


def _tempo(flat: stream.Stream, score: stream.Score) -> float:
    marks = list(flat.getElementsByClass(tempo.MetronomeMark))
    if not marks:
        marks = list(score.flatten().getElementsByClass(tempo.MetronomeMark))
    for mark in marks:
        bpm = mark.getQuarterBPM()
        if bpm:
            return float(bpm)
    return 120.0


def _time_signature(flat: stream.Stream) -> TimeSignature:
    ts = flat.getElementsByClass(meter.TimeSignature).first()
    if ts is None:
        return TimeSignature()
    return TimeSignature(numerator=ts.numerator, denominator=ts.denominator)


def _events(flat: stream.Stream) -> list[ChordEvent]:
    """Group simultaneous notes by offset; tie continuations extend the previous event."""
    by_offset: dict[Fraction, list[note.GeneralNote]] = {}
    for el in flat.notesAndRests:
        if isinstance(el, note.Unpitched):
            continue
        by_offset.setdefault(Fraction(el.offset), []).append(el)

    events: list[ChordEvent] = []
    cursor = Fraction(0)
    for offset in sorted(by_offset):
        group = by_offset[offset]
        start = offset / 4
        pitched = [el for el in group if not el.isRest]
        pitches = tuple(sorted({p.midi for el in pitched for p in _pitches(el)}))
        duration = max(Fraction(el.duration.quarterLength) for el in group) / 4
        if duration <= 0 or start < cursor:
            continue
        if start > cursor:
            events.append(ChordEvent((), start - cursor, len(events)))
        cursor = start + duration
        if _continues_previous(pitches, pitched, events):
            prev = events[-1]
            events[-1] = ChordEvent(prev.pitches, prev.duration + duration, prev.index, prev.meta)
            continue
        events.append(ChordEvent(pitches, duration, len(events), _meta(group)))
    return events


def _continues_previous(
    pitches: tuple[int, ...], pitched: list[note.GeneralNote], events: list[ChordEvent]
) -> bool:
    if not pitches or not events or events[-1].pitches != pitches:
        return False
    return all(el.tie is not None and el.tie.type in ("stop", "continue") for el in pitched)


def _pitches(el: note.GeneralNote) -> list:
    if isinstance(el, m21chord.Chord):
        return list(el.pitches)
    return [el.pitch] if isinstance(el, note.Note) else []


def _meta(group: list[note.GeneralNote]) -> dict:
    meta: dict = {}
    for el in group:
        for lyric in el.lyrics or []:
            if lyric.text:
                meta["text"] = lyric.text
    return meta
