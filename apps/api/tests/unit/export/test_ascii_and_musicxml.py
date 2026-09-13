from __future__ import annotations

from pathlib import Path

from music21 import converter

from guitarista_api.services.export import tab_to_ascii, tab_to_musicxml
from guitarista_api.services.score_service import score_file_to_tab


def test_ascii_has_six_lines_per_block_and_frets(twinkle_path: Path) -> None:
    tab = score_file_to_tab(twinkle_path)
    text = tab_to_ascii(tab)
    block = text.split("\n\n")[1].splitlines()
    assert len(block) == 6
    assert block[0].startswith("E |") and block[5].startswith("E |")
    assert "1--1" in block[1] and "3--3" in block[0]


def test_musicxml_roundtrips_pitches(twinkle_path: Path) -> None:
    tab = score_file_to_tab(twinkle_path)
    xml = tab_to_musicxml(tab)
    assert "<string>" in xml and "<fret>" in xml and "<work-title>" in xml
    score = converter.parse(xml, format="musicxml")
    pitches = [p.midi for el in score.flatten().notes for p in el.pitches]
    expected = [
        n.pitch_midi for m in tab.tracks[0].measures for b in m.voices[0].beats for n in b.notes
    ]
    assert pitches == expected
