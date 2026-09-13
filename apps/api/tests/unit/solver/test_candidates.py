from __future__ import annotations

import pytest

from guitarista_api.solver.candidates import CandidateConfig, NoValidFretting, enumerate_frettings
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent, NoteFretting

CFG = StringConfig()


def _pairs(frettings):
    return {tuple((n.string, n.fret) for n in f.notes) for f in frettings}


def test_low_e_has_exactly_one_fretting() -> None:
    out = enumerate_frettings(ChordEvent((40,)), CFG)
    assert _pairs(out) == {((6, 0),)}


def test_e4_positions_within_15_frets() -> None:
    out = enumerate_frettings(ChordEvent((64,)), CFG, CandidateConfig(max_fret=15))
    assert _pairs(out) == {((1, 0),), ((2, 5),), ((3, 9),), ((4, 14),)}


def test_rest_yields_single_rest_fretting() -> None:
    out = enumerate_frettings(ChordEvent(()), CFG)
    assert len(out) == 1 and out[0].is_rest()


def test_span_filter_removes_wide_chords() -> None:
    # C3 (48) + B3 (59): the (5,3)+(2,0) voicing is fine; (6,8)+(3,4) spans 4; (6,8)+(4,9) fine
    out = enumerate_frettings(ChordEvent((48, 59)), CFG, CandidateConfig(max_fret_span=2))
    assert all(f.fret_span <= 2 for f in out)
    wide = enumerate_frettings(ChordEvent((48, 59)), CFG, CandidateConfig(max_fret_span=20))
    assert len(wide) > len(out)


def test_fallback_to_unfiltered_when_filter_empties() -> None:
    # a 5-fret span chord with no compact alternative: E2 (40) + A#2 (46) -> (6,0)+(5,1)? no...
    # use pitches that force a wide span: F2 (41, only 6th string fret 1) + E4 (64) capped at 5
    out = enumerate_frettings(
        ChordEvent((41, 50)), CFG, CandidateConfig(max_fret=5, max_fret_span=0)
    )
    assert out  # unfiltered fallback rather than empty


def test_no_valid_fretting_raises() -> None:
    with pytest.raises(NoValidFretting):
        enumerate_frettings(ChordEvent((30,)), CFG)
    with pytest.raises(NoValidFretting):
        enumerate_frettings(ChordEvent((40, 41)), CFG)  # both only on string 6


def test_barre_aware_finger_count() -> None:
    from guitarista_api.solver.model import ChordFretting

    f = ChordFretting(tuple(NoteFretting(s, 5) for s in range(1, 7)))
    assert f.finger_count == 1 and f.fret_span == 0


def test_hint_misses_are_counted_per_note() -> None:
    from fractions import Fraction

    from guitarista_api.solver.candidates import enumerate_frettings
    from guitarista_api.solver.instrument import StringConfig
    from guitarista_api.solver.model import ChordEvent

    chord = ChordEvent((45, 64), Fraction(1, 4), 0, {"hints": {45: (6, 5), 64: (1, 0)}})
    cands = {
        tuple((n.string, n.fret) for n in f.notes): f.hint_misses
        for f in enumerate_frettings(chord, StringConfig())
    }
    assert cands[((1, 0), (6, 5))] == 0
    assert cands[((1, 0), (5, 0))] == 1  # A2 open instead of the hinted fret 5
    assert cands[((2, 5), (5, 0))] == 2
