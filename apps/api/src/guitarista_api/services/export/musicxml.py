"""Export a Tab track to MusicXML via music21 with string/fret technical indications."""

from __future__ import annotations

from music21 import (
    articulations,
    chord,
    clef,
    instrument,
    metadata,
    meter,
    note,
    stream,
    tempo,
    tie,
)
from music21.musicxml.m21ToXml import GeneralObjectExporter

from guitarista_api.domain.tab import Beat, Tab, Track


def tab_to_musicxml(tab: Tab, track_index: int = 0) -> str:
    if not tab.tracks:
        raise ValueError("tab has no tracks")
    track = tab.tracks[track_index]
    score = stream.Score()
    score.metadata = _metadata(tab)
    part = stream.Part(id="P1")
    part.partName = track.name
    inst = instrument.AcousticGuitar()
    inst.partName = track.name
    part.insert(0, inst)
    for i, measure in enumerate(track.measures):
        m = stream.Measure(number=measure.number)
        ts = measure.time_signature
        if i == 0:
            m.append(clef.TabClef())
            ts = ts or tab.time_signature
            m.append(tempo.MetronomeMark(number=tab.tempo_bpm))
        if ts is not None:
            m.append(meter.TimeSignature(f"{ts.numerator}/{ts.denominator}"))
        for beat in measure.voices[0].beats:
            m.append(_element(beat, track))
        part.append(m)
    score.append(part)
    return GeneralObjectExporter(score).parse().decode("utf-8")


def _metadata(tab: Tab) -> metadata.Metadata:
    md = metadata.Metadata()
    md.title = tab.title
    if tab.artist:
        md.composer = tab.artist
    return md


def _element(beat: Beat, track: Track) -> note.GeneralNote:
    ql = beat.duration.to_fraction() * 4
    if beat.is_rest:
        rest = note.Rest()
        rest.duration.quarterLength = ql
        return rest
    notes = [_note(n, track) for n in beat.notes]
    el: note.GeneralNote = notes[0] if len(notes) == 1 else chord.Chord(notes)
    el.duration.quarterLength = ql
    if beat.chord_name:
        el.lyric = beat.chord_name
    return el


def _note(n, track: Track) -> note.Note:
    pitch = (
        n.pitch_midi
        if n.pitch_midi is not None
        else track.tuning[n.string - 1] + track.capo + n.fret
    )
    m21n = note.Note(pitch)
    m21n.articulations.append(articulations.StringIndication(n.string))
    m21n.articulations.append(articulations.FretIndication(n.fret))
    if n.tie:
        m21n.tie = tie.Tie("stop")
    return m21n
