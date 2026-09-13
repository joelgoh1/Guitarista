from __future__ import annotations

from fractions import Fraction
from pathlib import Path

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
from guitarista_api.services.export.alphatex import tab_to_alphatex, tuning_names
from guitarista_api.services.score_service import score_file_to_tab
from guitarista_api.solver.to_tab import duration_from_fraction


def n(string: int, fret: int, **kw) -> Note:
    return Note(string=string, fret=fret, **kw)


def beat(*notes: Note, den: int = 4, **kw) -> Beat:
    return Beat(
        duration=Duration(den=den, **{k: kw.pop(k) for k in ("dots", "tuplet") if k in kw}),
        notes=list(notes),
        **kw,
    )


def make_tab(measures: list[Measure], **kw) -> Tab:
    return Tab(
        title=kw.pop("title", "Test"),
        tracks=[Track(measures=measures, **kw)],
        **{k: v for k, v in kw.items() if k in ("artist", "tempo_bpm", "time_signature")},
    )


def test_tuning_names_highest_first() -> None:
    assert tuning_names([64, 59, 55, 50, 45, 40]) == "e4 b3 g3 d3 a2 e2"
    assert tuning_names([64, 59, 55, 50, 45, 38]) == "e4 b3 g3 d3 a2 d2"


def test_header_and_single_notes_golden() -> None:
    tab = Tab(
        title='Say "Hi"',
        artist="Someone",
        tempo_bpm=90,
        tracks=[
            Track(
                capo=2,
                measures=[
                    Measure(
                        number=1,
                        time_signature=TimeSignature(),
                        voices=[
                            Voice(
                                beats=[
                                    beat(n(1, 0)),
                                    beat(n(6, 3)),
                                    beat(n(2, 1), den=8),
                                    beat(n(2, 1), den=8),
                                ]
                            )
                        ],
                    ),
                ],
            )
        ],
    )
    assert tab_to_alphatex(tab) == (
        '\\title "Say \\"Hi\\""\n'
        '\\artist "Someone"\n'
        "\\tempo 90\n"
        "\\tuning (e4 b3 g3 d3 a2 e2)\n"
        "\\capo 2\n"
        "\\ts 4 4\n"
        ".\n"
        "0.1.4 3.6 1.2.8 1.2\n"
    )


def test_string_numbers_are_canonical_not_flipped() -> None:
    # canonical string 1 = highest = alphaTex string 1; open high E must serialize as 0.1
    tab = make_tab([Measure(number=1, voices=[Voice(beats=[beat(n(1, 0)), beat(n(6, 0))])])])
    body = tab_to_alphatex(tab).splitlines()[-1]
    assert body == "0.1.4 0.6"


def test_chords_rests_dots_tuplets_ties_dead() -> None:
    measures = [
        Measure(
            number=1,
            voices=[
                Voice(
                    beats=[
                        beat(n(5, 3), n(4, 2), n(3, 0), n(2, 1), n(1, 0), den=2, chord_name="C"),
                        Beat(duration=Duration(den=4)),
                        beat(n(3, 2), den=8, dots=1),
                        beat(n(3, 2, tie=True), den=16),
                    ]
                )
            ],
        ),
        Measure(
            number=2,
            voices=[
                Voice(
                    beats=[
                        beat(n(1, 5), den=4, tuplet=(3, 2)),
                        beat(n(1, 7), den=4, tuplet=(3, 2)),
                        beat(n(1, 8), den=4, tuplet=(3, 2)),
                        beat(n(2, 0, dead=True), den=2),
                        Beat(duration=Duration(den=4), tempo_bpm=140),
                    ]
                )
            ],
        ),
    ]
    out = tab_to_alphatex(make_tab(measures))
    body = out.split(".\n", 1)[1]
    assert body == (
        '(3.5 2.4 0.3 1.2 0.1).2 {ch "C"} r.4 2.3.8 {d} -.3.16 |\n'
        "5.1.4 {tu 3} 7.1 {tu 3} 8.1 {tu 3} x.2.2 r.4 {tempo 140}\n"
    )


def test_time_signature_change_and_repeats_and_marker() -> None:
    measures = [
        Measure(number=1, repeat_start=True, voices=[Voice(beats=[beat(n(1, 0))] * 4)]),
        Measure(
            number=2,
            time_signature=TimeSignature(numerator=3, denominator=4),
            marker="B",
            repeat_end=2,
            voices=[Voice(beats=[beat(n(1, 0))] * 3)],
        ),
    ]
    body = tab_to_alphatex(make_tab(measures)).split(".\n", 1)[1]
    assert body == '\\ro 0.1.4 0.1 0.1 0.1 |\n\\ts 3 4 \\rc 2 \\section "B" 0.1 0.1 0.1\n'


def test_multiple_voices() -> None:
    measures = [
        Measure(
            number=1,
            voices=[
                Voice(beats=[beat(n(1, 0), den=1)]),
                Voice(beats=[beat(n(6, 0), den=2), beat(n(6, 3), den=2)]),
            ],
        )
    ]
    body = tab_to_alphatex(make_tab(measures)).split(".\n", 1)[1]
    assert body == "\\voice\n0.1.1\n\\voice\n0.6.2 3.6\n"


def test_duration_from_fraction_detection() -> None:
    assert duration_from_fraction(Fraction(1, 4)) == (Duration(den=4), None)
    assert duration_from_fraction(Fraction(3, 8)) == (Duration(den=4, dots=1), None)
    assert duration_from_fraction(Fraction(7, 16)) == (Duration(den=4, dots=2), None)
    assert duration_from_fraction(Fraction(1, 6)) == (Duration(den=4, tuplet=(3, 2)), None)
    d, warn = duration_from_fraction(Fraction(5, 16))
    assert d == Duration(den=4) and warn


def test_twinkle_golden_first_two_bars(twinkle_path: Path) -> None:
    tab = score_file_to_tab(twinkle_path, fallback_title="Twinkle")
    lines = tab_to_alphatex(tab).splitlines()
    assert lines[:5] == [
        '\\title "Twinkle"',
        "\\tempo 120",
        "\\tuning (e4 b3 g3 d3 a2 e2)",
        "\\ts 4 4",
        ".",
    ]
    assert lines[5] == "1.2.4 1.2 3.1 3.1 |"
    assert lines[6] == "5.1 5.1 3.1.2 |"
    assert len(tab.tracks[0].measures) == 12
