"""Convert Songsterr track JSON into the canonical ``Tab`` model.

Conventions bridged here:

* Songsterr ``note.string`` is 0-based with 0 = highest string; canonical is 1-based, 1 = highest,
  so we map ``s + 1``. ``tuning`` is already high→low MIDI in both models.
* ``beat.duration`` is ``[num, den]`` of a whole note. Dots are flagged (``dots``/``dotted``) and
  also baked into the fraction (``[3, 16]`` = dotted eighth); tuplets appear as non-power-of-two
  denominators (``[1, 12]`` = eighth-note triplet member).
* Tempo lives in ``automations.tempo``; the first entry is the tab tempo, later ones become
  ``Beat.tempo_bpm`` at ``(measure, position)``. ``position`` is treated as a beat index within
  the measure (observed only as 0 so far — see fixtures README).
* Capo is top-level on the track. ``Note.pitch_midi`` is derived so ``validate_tab`` can check it.
"""

from __future__ import annotations

from fractions import Fraction

import structlog

from guitarista_api.adapters.songsterr.schema import (
    Meta,
    TrackBeat,
    TrackJson,
    TrackMeasure,
    TrackNote,
)
from guitarista_api.domain.enums import TabSourceKind
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import (
    Beat,
    Duration,
    Measure,
    Note,
    Tab,
    TimeSignature,
    Track,
    Voice,
)
from guitarista_api.domain.validate import validate_tab

log = structlog.get_logger(__name__)

DRUM_INSTRUMENT_MIN = 112
_POWERS = [Fraction(1, 2**k) for k in range(0, 7)]  # whole .. 64th
_TUPLETS = [(3, 2), (5, 4), (6, 4), (7, 4), (9, 8)]


class ConversionError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


# --------------------------------------------------------------------------- track selection


def is_drum_track(instrument_id: int, instrument: str) -> bool:
    return instrument_id >= DRUM_INSTRUMENT_MIN or "drum" in instrument.lower()


def eligible_track_indices(meta: Meta) -> list[int]:
    """Indices of importable tracks, popular guitar track first, then meta order.

    Skips vocal, empty and (for now) drum tracks. Drums have no string/fret semantics; a later
    phase may map them to a percussion staff.
    """
    keep = [
        i
        for i, t in enumerate(meta.tracks)
        if not t.isVocalTrack and not t.isEmpty and not is_drum_track(t.instrumentId, t.instrument)
    ]
    preferred = meta.popularTrackGuitar
    if preferred is None or preferred not in keep:
        preferred = meta.popularTrack if meta.popularTrack in keep else None
    if preferred is not None:
        keep.remove(preferred)
        keep.insert(0, preferred)
    return keep


# --------------------------------------------------------------------------- durations


def convert_duration(beat: TrackBeat, warnings: list[str], where: str) -> Duration:
    num, den = (beat.duration + [1, 4])[:2] if beat.duration else (1, 4)
    if num <= 0 or den <= 0:
        warnings.append(f"{where}: invalid duration {beat.duration}, using quarter")
        return Duration()
    value = Fraction(num, den)
    dots = beat.dots or (1 if beat.dotted else 0)
    if dots:
        base = value / (2 - Fraction(1, 2**dots))  # undo 1.5x / 1.75x
        if base in _POWERS:
            return Duration(num=1, den=base.denominator, dots=dots)
    for base in _POWERS:
        if value == base:
            return Duration(num=1, den=base.denominator)
        if value == base * Fraction(3, 2):
            return Duration(num=1, den=base.denominator, dots=1)
        if value == base * Fraction(7, 4):
            return Duration(num=1, den=base.denominator, dots=2)
        for actual, normal in _TUPLETS:
            if value == base * Fraction(normal, actual):
                return Duration(num=1, den=base.denominator, tuplet=(actual, normal))
    nearest = min(_POWERS, key=lambda b: abs(b - value))
    warnings.append(f"{where}: duration {num}/{den} approximated as 1/{nearest.denominator}")
    return Duration(num=1, den=nearest.denominator)


# --------------------------------------------------------------------------- notes / beats


def _note_tech(note: TrackNote, beat: TrackBeat) -> list[str]:
    tech: list[str] = []
    if note.hp:
        tech.append("hammer")
    if note.slide:
        tech.append("slide")
    if note.bend:
        tech.append("bend")
    if note.vibrato:
        tech.append("vibrato")
    if note.palmMute or beat.palmMute:
        tech.append("palm_mute")
    if note.harmonic:
        tech.append("harmonic")
    if note.letRing or beat.letRing:
        tech.append("let_ring")
    if note.staccato:
        tech.append("staccato")
    if note.accentuated:
        tech.append("accent")
    if note.tremolo:
        tech.append("tremolo")
    if note.tapping:
        tech.append("tapping")
    return tech


def convert_note(
    note: TrackNote, beat: TrackBeat, tuning: list[int], capo: int, warnings: list[str], where: str
) -> Note | None:
    if note.rest or note.string is None:
        return None
    string = note.string + 1
    if not 1 <= string <= len(tuning):
        warnings.append(f"{where}: dropped note on string {note.string} (track has {len(tuning)})")
        return None
    fret = note.fret if note.fret is not None else 0
    if fret < 0 or fret > 30:
        warnings.append(f"{where}: dropped note with fret {fret}")
        return None
    dead = note.dead
    return Note(
        string=string,
        fret=fret,
        pitch_midi=None if dead else tuning[string - 1] + capo + fret,
        tie=note.tie,
        dead=dead,
        ghost=note.ghost,
        tech=_note_tech(note, beat),
    )


def convert_beat(
    beat: TrackBeat, tuning: list[int], capo: int, warnings: list[str], where: str
) -> Beat:
    duration = convert_duration(beat, warnings, where)
    notes: list[Note] = []
    if not beat.rest:
        seen: set[int] = set()
        for raw in beat.notes:
            note = convert_note(raw, beat, tuning, capo, warnings, where)
            if note is None:
                continue
            if note.string in seen:
                warnings.append(f"{where}: duplicate string {note.string} in beat, kept first")
                continue
            seen.add(note.string)
            notes.append(note)
    chord = beat.chord.text.strip() if beat.chord and beat.chord.text else None
    return Beat(
        duration=duration,
        notes=notes,
        chord_name=chord or None,
        text=beat.text or None,
        tempo_bpm=beat.tempo,
    )


# --------------------------------------------------------------------------- measures / track


def _time_signature(measure: TrackMeasure) -> TimeSignature | None:
    if measure.signature and len(measure.signature) >= 2 and all(measure.signature[:2]):
        return TimeSignature(numerator=measure.signature[0], denominator=measure.signature[1])
    return None


def _live_voice_indices(track: TrackJson) -> list[int]:
    """Voices that contain at least one sounding beat anywhere in the track (min. voice 0)."""
    live: set[int] = set()
    for measure in track.measures:
        for v_idx, voice in enumerate(measure.voices):
            if any(not b.rest and any(not n.rest for n in b.notes) for b in voice.beats):
                live.add(v_idx)
    return sorted(live) or [0]


def convert_track(track: TrackJson, track_label: str, warnings: list[str]) -> Track:
    tuning = list(track.tuning)
    capo = max(track.capo, 0)
    voice_indices = _live_voice_indices(track)
    tempo_changes = {
        (a.measure, a.position): a.bpm for a in track.automations.tempo[1:] if a.bpm > 0
    }
    measures: list[Measure] = []
    current_ts: TimeSignature | None = None
    for m_idx, raw_measure in enumerate(track.measures):
        voices: list[Voice] = []
        for v_idx in voice_indices:
            raw_voice = raw_measure.voices[v_idx] if v_idx < len(raw_measure.voices) else None
            beats = [
                convert_beat(
                    b, tuning, capo, warnings, f"{track_label} m{m_idx + 1} v{v_idx} b{b_idx}"
                )
                for b_idx, b in enumerate(raw_voice.beats if raw_voice else [])
            ]
            voices.append(Voice(beats=beats))
        for (m, pos), bpm in tempo_changes.items():
            if m == m_idx and voices and voices[0].beats:
                beats0 = voices[0].beats
                beats0[min(pos, len(beats0) - 1)].tempo_bpm = bpm
        ts = _time_signature(raw_measure)
        changed = ts is not None and (current_ts is None or ts != current_ts)
        if changed:
            current_ts = ts
        measures.append(
            Measure(
                number=m_idx + 1,
                time_signature=ts if changed else None,
                voices=voices,
                marker=(raw_measure.marker.text.strip() or None) if raw_measure.marker else None,
                repeat_start=raw_measure.repeatStart,
                repeat_end=raw_measure.repeat if raw_measure.repeat else None,
            )
        )
    return Track(
        name=track.name.strip() or track.instrument or "Track",
        instrument=track.instrument or "unknown",
        tuning=tuning,
        capo=capo,
        measures=measures,
    )


def songsterr_to_tab(meta: Meta, tracks: list[tuple[int, TrackJson]], song: Song | None) -> Tab:
    """Build a validated ``Tab`` from Songsterr meta + fetched tracks (index order preserved)."""
    if not tracks:
        raise ConversionError("no importable tracks")
    warnings: list[str] = []
    converted = [convert_track(tj, f"track {idx}", warnings) for idx, tj in tracks]
    first = tracks[0][1]
    tempo = next((a.bpm for a in first.automations.tempo if a.bpm > 0), None)
    if tempo is None:
        tempo = 120.0
        warnings.append("no tempo automation found, defaulting to 120 bpm")
    first_ts = next((ts for m in first.measures if (ts := _time_signature(m))), TimeSignature())
    indices = ",".join(str(i) for i, _ in tracks)
    tab = Tab(
        song_id=song.id if song else None,
        title=meta.title or (song.title if song else "Untitled"),
        artist=meta.artist or (song.artist if song else None) or None,
        source=TabSourceKind.SONGSTERR,
        source_ref=f"songsterr:{meta.songId}:{meta.revisionId}:{indices}",
        confidence=1.0,
        tempo_bpm=tempo,
        time_signature=first_ts,
        tracks=converted,
        warnings=_dedupe(warnings),
    )
    errors = validate_tab(tab)
    if errors:
        raise ConversionError(f"converted tab failed validation ({len(errors)} errors)", errors)
    return tab


def _dedupe(items: list[str], limit: int = 50) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    if len(out) > limit:
        out = out[:limit] + [f"... {len(out) - limit} more warnings"]
    return out
