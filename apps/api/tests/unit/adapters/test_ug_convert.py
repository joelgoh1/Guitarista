from __future__ import annotations

from pathlib import Path

import pytest

from guitarista_api.adapters.ultimate_guitar.convert import (
    UGConvertError,
    ascii_to_tab,
    chords_to_tab,
    page_to_tab,
    parse_ascii_tab,
    parse_tuning_names,
)
from guitarista_api.adapters.ultimate_guitar.parse import UGTabPage, extract_store, parse_tab_page
from guitarista_api.domain.validate import validate_tab
from guitarista_api.services.chord_voicings import parse_chord_symbol, voicing_for
from guitarista_api.services.export.alphatex import tab_to_alphatex

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ug"


def _page(name: str) -> UGTabPage:
    return parse_tab_page(extract_store((FIXTURES / name).read_text()))


def test_parse_tuning_names_low_to_high_becomes_high_to_low_midi() -> None:
    assert parse_tuning_names("E A D G B E") == [64, 59, 55, 50, 45, 40]
    assert parse_tuning_names("D A D G B E") == [64, 59, 55, 50, 45, 38]
    assert parse_tuning_names("Eb Ab Db Gb Bb Eb") == [63, 58, 54, 49, 44, 39]
    assert parse_tuning_names("B E A D G B E") == [64, 59, 55, 50, 45, 40, 35]
    assert parse_tuning_names("weird") is None and parse_tuning_names(None) is None


def test_chord_voicings() -> None:
    assert parse_chord_symbol("F#m7/A") == (6, "m7")
    assert parse_chord_symbol("Bbmaj7") == (10, "maj7")
    assert parse_chord_symbol("hello") is None
    assert voicing_for("C") == ((5, 3), (4, 2), (3, 0), (2, 1), (1, 0))
    assert voicing_for("F#m7") == ((6, 2), (5, 4), (4, 2), (3, 2), (2, 2), (1, 2))  # E-shape barre
    assert voicing_for("Bm") == ((5, 2), (4, 4), (3, 4), (2, 3), (1, 2))
    assert voicing_for("Csus2") is not None and voicing_for("Gm") is not None
    assert voicing_for("Cmaj13#11") is None and voicing_for("N.C.") is None


def test_tabs_page_converts_and_validates() -> None:
    tab = page_to_tab(_page("tab_tabs.html"))
    assert validate_tab(tab) == []
    assert tab.source == "ultimate_guitar" and tab.source_ref == "ug:2223387"
    assert tab.confidence == 0.6 and tab.tempo_bpm == 100
    track = tab.tracks[0]
    assert track.capo == 2 and track.tuning == [64, 59, 55, 50, 45, 40]
    first = track.measures[0].voices[0].beats[0]
    assert first.duration.den == 8
    assert {(n.string, n.fret) for n in first.notes} == {
        (1, 3),
        (2, 3),
        (3, 0),
        (4, 2),
        (5, 2),
        (6, 0),
    }
    assert first.notes[0].pitch_midi == 64 + 2 + 3
    assert all(len(m.voices[0].beats) <= 8 for m in track.measures)
    tex = tab_to_alphatex(tab)
    assert tex.startswith('\\title "Wonderwall"') and "\\capo 2" in tex
    assert "(3.1 3.2 0.3 2.4 2.5 0.6).8" in tex


def test_chords_page_converts_and_validates() -> None:
    tab = page_to_tab(_page("tab_chords_6125.html"))
    assert validate_tab(tab) == []
    assert tab.confidence == 0.6 and tab.tracks[0].capo == 0
    measures = tab.tracks[0].measures
    assert measures[0].marker == "Intro"
    names = [b.chord_name for b in measures[0].voices[0].beats]
    assert names == ["F#m7", "A", "Esus4", "B7sus4"]
    assert all(b.duration.den == 4 for b in measures[0].voices[0].beats)
    assert all(b.notes for b in measures[0].voices[0].beats)  # every intro chord has a voicing
    assert any(m.marker == "Verse 1" for m in measures)
    # lyric lines never became beats
    assert all(b.chord_name for m in measures for b in m.voices[0].beats)
    tex = tab_to_alphatex(tab)
    assert '{ch "F#m7"}' in tex and '\\section "Intro"' in tex


def test_unknown_chord_keeps_name_with_warning() -> None:
    page = UGTabPage(
        id=1,
        song_name="X",
        artist_name="Y",
        type="Chords",
        tuning_value="E A D G B E",
        content="[Verse]\n[ch]Cmaj13#11[/ch] [ch]G[/ch]\n",
    )
    tab = chords_to_tab(page)
    beats = tab.tracks[0].measures[0].voices[0].beats
    assert beats[0].chord_name == "Cmaj13#11" and beats[0].notes == []
    assert beats[1].notes
    assert any("Cmaj13#11" in w for w in tab.warnings)
    assert validate_tab(tab) == []
    with pytest.raises(UGConvertError):
        chords_to_tab(UGTabPage(id=2, song_name="", artist_name="", type="Chords", content="la la"))


def test_ascii_parser_two_digit_frets_bars_and_techniques() -> None:
    content = (
        "[tab]e|--12--|--1-2--|\n"
        "B|------|--3-3--|\n"
        "G|--x---|-------|\n"
        "D|------|--5h7--|\n"
        "A|------|-------|\n"
        "E|-0----|-------|[/tab]"
    )
    parsed = parse_ascii_tab(content)
    beats = parsed.beats
    assert [len(m) for m in parsed.measures] == [2, 2]
    assert (beats[0].notes[0].string, beats[0].notes[0].fret) == (6, 0)
    assert beats[1].notes[0].fret == 12 and beats[1].notes[1].dead  # 12 = one fret, x = dead
    third = {n.string: n.fret for n in beats[2].notes}
    assert third == {1: 1, 2: 3, 4: 5}  # "1-2" with digits under it stays two beats
    assert beats[3].notes[0].fret == 2
    hammer = next(n for n in beats[2].notes if n.string == 4)
    assert "hammer" in hammer.tech


def test_ascii_too_few_notes_raises() -> None:
    page = UGTabPage(
        id=3,
        song_name="",
        artist_name="",
        type="Tabs",
        content="[tab]e|--3--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|[/tab]",
    )
    with pytest.raises(UGConvertError):
        ascii_to_tab(page)
