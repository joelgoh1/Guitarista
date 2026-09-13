from __future__ import annotations

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from guitarista_api.solver.candidates import CandidateConfig, enumerate_frettings
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent
from guitarista_api.solver.search import solve

CFG = StringConfig()
LO, HI = CFG.pitch_range(15)

pitch = st.integers(min_value=LO, max_value=HI)
chord = st.lists(pitch, min_size=1, max_size=4, unique=True).map(tuple)
sequence = st.lists(chord | st.just(()), min_size=1, max_size=12)


@given(sequence)
@settings(max_examples=60, deadline=None)
def test_solution_sounds_exactly_the_input(seq: list[tuple[int, ...]]) -> None:
    chords = [ChordEvent(p, Fraction(1, 8), i) for i, p in enumerate(seq)]
    try:
        res = solve(chords, CFG)
    except Exception as exc:  # only NoValidFretting is acceptable
        from guitarista_api.solver.candidates import NoValidFretting

        assert isinstance(exc, NoValidFretting)
        return
    assert len(res.frettings) == len(chords)
    for c, f in zip(chords, res.frettings, strict=True):
        sounding = tuple(sorted(CFG.pitch_at(n.string, n.fret) for n in f.notes))
        assert sounding == c.pitches
        assert len({n.string for n in f.notes}) == len(f.notes)
        assert all(0 <= n.fret <= 15 for n in f.notes)
    assert res.total_cost == sum(res.per_step_cost)


@given(chord)
@settings(max_examples=60, deadline=None)
def test_candidates_are_unique_and_consistent(pitches: tuple[int, ...]) -> None:
    from guitarista_api.solver.candidates import NoValidFretting

    try:
        out = enumerate_frettings(ChordEvent(pitches), CFG, CandidateConfig())
    except NoValidFretting:
        return
    assert len({f.notes for f in out}) == len(out)
    for f in out:
        assert tuple(sorted(CFG.pitch_at(n.string, n.fret) for n in f.notes)) == tuple(
            sorted(pitches)
        )
