from __future__ import annotations

from fractions import Fraction

from guitarista_api.domain.transcription import NoteEvent
from guitarista_api.solver.quantize import Grid, estimate_grid, quantize

SIXTEENTH = Fraction(1, 16)


def note(onset: float, offset: float, pitch: int = 64, **kw: float) -> NoteEvent:
    return NoteEvent(pitch_midi=pitch, onset_s=onset, offset_s=offset, **kw)


def melody(onsets: list[float], length: float, pitch: int = 64) -> list[NoteEvent]:
    return [note(o, o + length, pitch) for o in onsets]


def rests(events) -> int:
    return sum(1 for e in events if e.is_rest)


def test_constant_grid_matches_bare_tempo() -> None:
    grid = estimate_grid([], 120.0)
    assert grid.beats_s == () and grid.step_s == 0.125
    assert grid.snap(0.5) == 4 and grid.snap(0.56) == 4 and grid.snap(0.59) == 5


def test_beat_map_tempo_and_phase() -> None:
    # beats every 0.5 s starting at 0.13 s: the phase offset must not produce rounding jitter
    beats = [0.13 + 0.5 * k for k in range(8)]
    grid = estimate_grid([], None, beats_s=beats)
    assert grid.tempo_bpm == 120.0
    assert [grid.snap(b) for b in beats] == [4 * k for k in range(8)]
    assert grid.snap(0.13 + 0.25) == 2  # halfway between beats = eighth note
    assert grid.snap(0.0) < 0  # before the first beat, extrapolated


def test_beat_map_follows_tempo_drift() -> None:
    beats = [0.0, 0.5, 1.0, 1.6, 2.2, 2.8]  # slows down after beat 2
    grid = Grid(120.0, beats_s=tuple(beats))
    assert grid.snap(1.3) == 10  # halfway through the 0.6 s beat is still an eighth note
    assert grid.snap(2.5) == 18


def test_clean_beats_drops_duplicates_and_negatives() -> None:
    grid = estimate_grid([], 100.0, beats_s=[-0.2, 0.6, 0.6, 0.62, 1.2])
    assert grid.beats_s == (0.6, 1.2)


def test_phase_offset_melody_has_no_spurious_rests() -> None:
    beats = [0.13 + 0.5 * k for k in range(9)]
    notes = melody(beats[:8], 0.35)  # notes end early, as transcribers do
    grid = estimate_grid(notes, None, beats_s=beats)
    events = quantize(notes, grid)
    assert rests(events) == 0
    assert all(e.duration == Fraction(1, 4) for e in events)


def test_early_offsets_are_legato_filled_by_default() -> None:
    grid = Grid(120.0)  # step 0.125 s
    notes = melody([0.0, 0.5, 1.0], 0.3)  # each ends 0.2 s (~2 steps) before the next onset
    events = quantize(notes, grid)
    assert rests(events) == 0
    assert [e.duration for e in events] == [Fraction(1, 4)] * 3


def test_long_gaps_stay_rests() -> None:
    grid = Grid(120.0)
    notes = [note(0.0, 0.25), note(1.5, 1.75)]  # 1.25 s silence = 10 steps
    events = quantize(notes, grid)
    assert [e.is_rest for e in events] == [False, True, False]
    assert events[1].duration == 10 * SIXTEENTH


def test_fill_gap_can_be_disabled() -> None:
    grid = Grid(120.0)
    notes = melody([0.0, 0.5], 0.3)
    events = quantize(notes, grid, fill_gap_steps=0)
    assert rests(events) == 1


def test_strum_becomes_one_chord() -> None:
    grid = Grid(120.0)
    pitches = [40, 45, 50, 55, 59, 64]
    strum = [note(0.012 * i, 1.0, p) for i, p in enumerate(pitches)]  # 60 ms spread
    events = quantize(strum, grid)
    assert len(events) == 1 and events[0].pitches == tuple(pitches)


def test_slow_arpeggio_stays_separate() -> None:
    grid = Grid(120.0)
    arp = [note(0.25 * i, 0.25 * i + 0.2, p) for i, p in enumerate([40, 47, 52])]
    events = quantize(arp, grid)
    assert [e.pitches for e in events] == [(40,), (47,), (52,)]


def test_group_span_cap_splits_long_chains() -> None:
    grid = Grid(120.0)
    chain = [note(0.04 * i, 1.0, 40 + i) for i in range(6)]  # 40 ms apart, 200 ms total
    events = quantize(chain, grid, min_gap_s=0.05, max_group_span_s=0.12)
    assert len(events) >= 2 and sum(len(e.pitches) for e in events) == 6


def test_notes_before_first_beat_shift_grid_origin() -> None:
    beats = [0.5 + 0.5 * k for k in range(4)]
    notes = melody([0.0, 0.5, 1.0], 0.4)
    events = quantize(notes, estimate_grid(notes, None, beats_s=beats))
    assert [e.is_rest for e in events] == [False, False, False]
    assert sum(e.duration for e in events) == Fraction(3, 4)


def test_polyphony_cap_prefers_confident_notes() -> None:
    grid = Grid(120.0)
    chord = [note(0.0, 0.5, 40 + i, confidence=0.1 * (i + 1)) for i in range(7)]
    events = quantize(chord, grid, max_polyphony=6)
    assert events[0].pitches == tuple(range(41, 47))


def test_string_hints_travel_in_chord_meta() -> None:
    grid = Grid(120.0)
    notes = [
        NoteEvent(pitch_midi=45, onset_s=0.0, offset_s=0.4, string=6, fret=5),
        NoteEvent(pitch_midi=52, onset_s=0.01, offset_s=0.4, string=5, fret=7),
        NoteEvent(pitch_midi=64, onset_s=0.5, offset_s=0.9),  # no hint
    ]
    events = quantize(notes, grid)
    assert events[0].pitches == (45, 52) and events[0].meta["hints"] == {45: (6, 5), 52: (5, 7)}
    assert "hints" not in events[1].meta
    assert [n.pitch_midi for n in events[0].meta["source_notes"]] == [45, 52]
