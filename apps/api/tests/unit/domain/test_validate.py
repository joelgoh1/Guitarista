from __future__ import annotations

from fractions import Fraction

from guitarista_api.domain.tab import Beat, Duration, Measure, Note, Tab, Track, Voice
from guitarista_api.domain.validate import validate_tab


def _tab(*notes: Note, capo: int = 0) -> Tab:
    return Tab(
        tracks=[
            Track(
                capo=capo,
                measures=[Measure(number=1, voices=[Voice(beats=[Beat(notes=list(notes))])])],
            )
        ]
    )


def test_valid_tab_has_no_errors() -> None:
    assert validate_tab(_tab(Note(string=1, fret=3, pitch_midi=67))) == []
    assert validate_tab(_tab(Note(string=6, fret=0, pitch_midi=42), capo=2)) == []


def test_pitch_mismatch_and_duplicates_and_range() -> None:
    errors = validate_tab(
        _tab(Note(string=1, fret=3, pitch_midi=60), Note(string=1, fret=5), Note(string=7, fret=0))
    )
    assert any("sounds 67" in e for e in errors)
    assert any("duplicate string 1" in e for e in errors)
    assert any("string 7 out of range" in e for e in errors)


def test_duration_fraction() -> None:
    assert Duration(den=8, dots=1).to_fraction() == Fraction(3, 16)
    assert Duration(den=4, tuplet=(3, 2)).to_fraction() == Fraction(1, 6)
