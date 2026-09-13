from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from guitarista_api.adapters.score_import import score_to_chord_events
from guitarista_api.solver.candidates import CandidateConfig
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent
from guitarista_api.solver.search import solve

CFG = StringConfig()


def events(*groups: tuple[int, ...] | int) -> list[ChordEvent]:
    out = []
    for i, g in enumerate(groups):
        pitches = (g,) if isinstance(g, int) else g
        out.append(ChordEvent(pitches, Fraction(1, 4), i))
    return out


def pairs(f) -> set[tuple[int, int]]:
    return {(n.string, n.fret) for n in f.notes}


def test_c_major_scale_stays_in_open_position() -> None:
    # C3..C4 is the open-position C scale on a standard guitar (C4..C5 needs fret 7+ for B4).
    scale = events(48, 50, 52, 53, 55, 57, 59, 60)
    res = solve(scale, CFG)
    frets = [f.notes[0].fret for f in res.frettings]
    assert all(0 <= fr <= 5 for fr in frets), frets
    positions = [f.hand_position for f in res.frettings if not f.all_open]
    assert max(positions) - min(positions) <= 3, positions


OPEN_CHORDS = {
    "C": ((48, 52, 55, 60, 64), {(5, 3), (4, 2), (3, 0), (2, 1), (1, 0)}),
    "G": ((43, 47, 50, 55, 59, 67), {(6, 3), (5, 2), (4, 0), (3, 0), (2, 0), (1, 3)}),
    "D": ((50, 57, 62, 66), {(4, 0), (3, 2), (2, 3), (1, 2)}),
    "A": ((45, 52, 57, 61, 64), {(5, 0), (4, 2), (3, 2), (2, 2), (1, 0)}),
    "E": ((40, 47, 52, 56, 59, 64), {(6, 0), (5, 2), (4, 2), (3, 1), (2, 0), (1, 0)}),
    "Em": ((40, 47, 52, 55, 59, 64), {(6, 0), (5, 2), (4, 2), (3, 0), (2, 0), (1, 0)}),
}


def test_open_chords_get_textbook_frettings() -> None:
    for name, (pitches, expected) in OPEN_CHORDS.items():
        res = solve(events(pitches), CFG)
        assert pairs(res.frettings[0]) == expected, name


def test_open_chord_progression_is_stable() -> None:
    chords = events(*(OPEN_CHORDS[n][0] for n in ("G", "D", "Em", "C")))
    res = solve(chords, CFG)
    for f, name in zip(res.frettings, ("G", "D", "Em", "C"), strict=True):
        assert pairs(f) == OPEN_CHORDS[name][1], name


def test_twinkle_solves_in_first_position(twinkle_path: Path) -> None:
    chords, meta = score_to_chord_events(twinkle_path)
    assert meta.tempo_bpm == 120 and (
        meta.time_signature.numerator,
        meta.time_signature.denominator,
    ) == (4, 4)
    res = solve(chords, CFG, ccfg=CandidateConfig(max_fret=15))
    assert len(res.frettings) == len(chords)
    assert sum(len(f.notes) for f in res.frettings) == sum(len(c.pitches) for c in chords) == 42
    for chord, f in zip(chords, res.frettings, strict=True):
        assert all(n.fret <= 5 for n in f.notes)
        for n in f.notes:
            assert CFG.check_consistency(n.string, n.fret, CFG.pitch_at(n.string, n.fret))
        assert tuple(sorted(CFG.pitch_at(n.string, n.fret) for n in f.notes)) == chord.pitches


def test_deterministic(twinkle_path: Path) -> None:
    chords, _ = score_to_chord_events(twinkle_path)
    a = solve(chords, CFG)
    b = solve(chords, CFG)
    assert [f.notes for f in a.frettings] == [f.notes for f in b.frettings]
    assert a.total_cost == b.total_cost


def test_viterbi_and_beam_agree_on_short_inputs() -> None:
    short = events(60, 62, 64, (60, 64, 67), 67, 69)
    v = solve(short, CFG, algorithm="viterbi")
    b = solve(short, CFG, algorithm="beam")
    assert abs(v.total_cost - b.total_cost) < 1e-9


def test_rests_carry_context() -> None:
    seq = [
        ChordEvent((67,), Fraction(1, 4), 0),
        ChordEvent((), Fraction(1, 4), 1),
        ChordEvent((67,), Fraction(1, 4), 2),
    ]
    res = solve(seq, CFG)
    assert res.frettings[1].is_rest()
    assert res.frettings[0].notes == res.frettings[2].notes


def test_out_of_range_policies() -> None:
    import pytest

    from guitarista_api.solver.candidates import NoValidFretting

    low = events(30, 60)
    with pytest.raises(NoValidFretting):
        solve(low, CFG)
    dropped = solve(low, CFG, out_of_range="drop")
    assert dropped.frettings[0].is_rest() and dropped.warnings
    shifted = solve(low, CFG, out_of_range="octave_shift")
    assert CFG.pitch_at(*[(n.string, n.fret) for n in shifted.frettings[0].notes][0]) == 42


def test_lead_profile_keeps_a_high_run_in_position() -> None:
    from guitarista_api.solver.cost import cost_for_profile

    # D5 C5 B4 A4 E4 A4 B4: frets 10-5 on string 1; E4 is the open high E or string 2 fret 5.
    run = events(74, 72, 71, 69, 64, 69, 71)
    tabgen = solve(run, CFG)
    lead = solve(run, CFG, cost=cost_for_profile("lead"))
    assert pairs(tabgen.frettings[4]) == {(1, 0)}  # classic heuristics jump to the open string
    assert pairs(lead.frettings[4]) == {(2, 5)}  # lead stays in position
    assert [pairs(f) for f in lead.frettings[:4]] == [{(1, 10)}, {(1, 8)}, {(1, 7)}, {(1, 5)}]


def test_lead_profile_still_uses_open_position_for_open_chords() -> None:
    from guitarista_api.solver.cost import cost_for_profile

    chords = events(*(OPEN_CHORDS[n][0] for n in ("G", "D", "Em", "C")))
    res = solve(chords, CFG, cost=cost_for_profile("lead"))
    for f, name in zip(res.frettings, ("G", "D", "Em", "C"), strict=True):
        assert pairs(f) == OPEN_CHORDS[name][1], name


def test_hints_steer_the_solver_but_keep_pitches() -> None:
    plain = events(40, 45, 50)
    res = solve(plain, CFG)
    assert [pairs(f) for f in res.frettings] == [{(6, 0)}, {(5, 0)}, {(4, 0)}]
    hinted = [
        ChordEvent(c.pitches, c.duration, c.index, {"hints": {c.pitches[0]: h}})
        for c, h in zip(plain, [(6, 0), (6, 5), (5, 5)], strict=True)
    ]
    res = solve(hinted, CFG)
    assert [pairs(f) for f in res.frettings] == [{(6, 0)}, {(6, 5)}, {(5, 5)}]
    assert [CFG.pitch_at(*next(iter(pairs(f)))) for f in res.frettings] == [40, 45, 50]
    # an impossible hint (wrong string for the pitch) is simply ignored by the candidate set
    bad = [ChordEvent((45,), Fraction(1, 4), 0, {"hints": {45: (1, 0)}})]
    assert pairs(solve(bad, CFG).frettings[0]) == {(5, 0)}


def test_unplayable_chords_are_repaired_unless_policy_is_raise() -> None:
    import pytest

    from guitarista_api.domain.transcription import NoteEvent
    from guitarista_api.solver.candidates import NoValidFretting

    # E2 and G#2 both live only on the low E string (fret 0 / 4): no hand can play both.
    clash = [ChordEvent((40, 44, 52, 59, 63, 68), Fraction(1, 4), 0)]
    with pytest.raises(NoValidFretting):
        solve(clash, CFG)
    res = solve(clash, CFG, out_of_range="octave_shift")
    assert len(res.frettings[0].notes) == 5 and res.warnings and "44" in res.warnings[0]
    # with source notes, confidence breaks the tie between the two colliding pitches
    notes = [
        NoteEvent(pitch_midi=p, onset_s=0, offset_s=1, confidence=c)
        for p, c in [(40, 0.2), (44, 0.9), (52, 0.8), (59, 0.8), (63, 0.8), (68, 0.8)]
    ]
    clash = [ChordEvent((40, 44, 52, 59, 63, 68), Fraction(1, 4), 0, {"source_notes": notes})]
    res = solve(clash, CFG, out_of_range="drop")
    assert res.chords[0].pitches == (44, 52, 59, 63, 68) and "40" in res.warnings[0]
    # more pitches than strings
    seven = [ChordEvent((40, 45, 50, 55, 59, 64, 69), Fraction(1, 4), 0)]
    assert len(solve(seven, CFG, out_of_range="drop").frettings[0].notes) == 6
