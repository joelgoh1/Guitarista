from __future__ import annotations

import pytest

from guitarista_api.adapters.songsterr.convert import (
    ConversionError,
    convert_duration,
    eligible_track_indices,
    songsterr_to_tab,
)
from guitarista_api.adapters.songsterr.schema import Meta, TrackBeat, TrackJson
from guitarista_api.domain.validate import validate_tab
from guitarista_api.services.export.alphatex import tab_to_alphatex


@pytest.fixture
def meta(songsterr_fixtures) -> Meta:
    return Meta.model_validate(songsterr_fixtures["meta"])


@pytest.fixture
def tracks(songsterr_fixtures) -> list[tuple[int, TrackJson]]:
    return [
        (3, TrackJson.model_validate(songsterr_fixtures["track_3"])),
        (6, TrackJson.model_validate(songsterr_fixtures["track_6"])),
    ]


def test_eligible_tracks_skip_vocals_and_drums_and_prefer_popular_guitar(meta: Meta) -> None:
    idx = eligible_track_indices(meta)
    assert idx[0] == meta.popularTrackGuitar == 3
    assert 0 not in idx and 1 not in idx  # vocals
    assert 7 not in idx  # instrumentId 123 (>= 112 treated as percussion)
    assert 6 in idx  # bass


def test_convert_rhythm_guitar_track(meta: Meta, tracks) -> None:
    tab = songsterr_to_tab(meta, tracks, None)
    assert tab.source == "songsterr"
    assert tab.source_ref == "songsterr:2:8047059:3,6"
    assert tab.confidence == 1.0
    assert tab.tempo_bpm == 88
    assert (tab.time_signature.numerator, tab.time_signature.denominator) == (4, 4)
    guitar = tab.tracks[0]
    assert guitar.capo == 2
    assert guitar.tuning == [64, 59, 55, 50, 45, 40]
    assert len(guitar.measures) == 94
    assert guitar.measures[0].marker == "Intro"
    first = guitar.measures[0].voices[0].beats[0]
    frets = {n.string: n.fret for n in first.notes}
    assert frets[1] == 3 and frets[2] == 3  # Em7 shape, canonical string 1 = highest
    assert first.chord_name == "Em7"
    assert first.duration.den == 8
    assert "let_ring" in first.notes[0].tech
    # pitch_midi is consistent with tuning + capo + fret
    assert first.notes[0].pitch_midi == 64 + 2 + 3
    assert validate_tab(tab) == []


def test_rests_ties_and_dotted_durations(meta: Meta, tracks) -> None:
    tab = songsterr_to_tab(meta, tracks, None)
    guitar, bass = tab.tracks
    assert bass.name.endswith("Bass") and bass.tuning == [43, 38, 33, 28]
    # bass starts with a whole-measure rest
    assert bass.measures[0].voices[0].beats[0].is_rest
    all_beats = [b for m in bass.measures for v in m.voices for b in v.beats]
    assert any(b.duration.dots == 1 and b.duration.den == 8 for b in all_beats)
    assert any(n.tie for b in all_beats for n in b.notes)
    assert any("staccato" in n.tech for b in all_beats for n in b.notes)
    assert any("slide" in n.tech for b in all_beats for n in b.notes)
    assert any(n.tie for m in guitar.measures for v in m.voices for b in v.beats for n in b.notes)


def test_alphatex_export_of_converted_tab(meta: Meta, tracks) -> None:
    tab = songsterr_to_tab(meta, tracks, None)
    for i in range(len(tab.tracks)):
        tex = tab_to_alphatex(tab, i)
        assert tex.startswith('\\title "Wonderwall"')
        # every fret.string token uses a string number within the track's range
        import re

        strings = {int(s) for s in re.findall(r"(?<![\w.])(?:\d+|x|-)\.(\d)(?=[\s{).|])", tex)}
        assert strings <= set(range(1, len(tab.tracks[i].tuning) + 1))
    assert "\\capo 2" in tab_to_alphatex(tab, 0)
    assert '\\section "Intro"' in tab_to_alphatex(tab, 0)


@pytest.mark.parametrize(
    ("beat", "expected"),
    [
        ({"duration": [1, 4]}, (4, 0, None)),
        ({"duration": [3, 16], "dots": 1}, (8, 1, None)),
        ({"duration": [3, 8]}, (4, 1, None)),
        ({"duration": [7, 16]}, (4, 2, None)),
        ({"duration": [1, 12]}, (8, 0, (3, 2))),
        ({"duration": [1, 6]}, (4, 0, (3, 2))),
        ({"duration": [1, 20]}, (16, 0, (5, 4))),
    ],
)
def test_convert_duration(beat, expected) -> None:
    warnings: list[str] = []
    d = convert_duration(TrackBeat.model_validate(beat), warnings, "x")
    assert (d.den, d.dots, d.tuplet) == expected
    assert warnings == []


def test_convert_duration_falls_back_with_warning() -> None:
    warnings: list[str] = []
    d = convert_duration(TrackBeat.model_validate({"duration": [5, 17]}), warnings, "m1")
    assert d.den in {2, 4}
    assert warnings and "approximated" in warnings[0]


def test_tempo_changes_and_techniques_are_mapped(meta: Meta) -> None:
    raw = {
        "name": "Lead",
        "capo": 0,
        "tuning": [64, 59, 55, 50, 45, 40],
        "instrumentId": 30,
        "instrument": "Distortion Guitar",
        "automations": {
            "tempo": [
                {"bpm": 120, "measure": 0, "position": 0},
                {"bpm": 140, "measure": 1, "position": 1},
            ]
        },
        "measures": [
            {
                "signature": [4, 4],
                "voices": [
                    {
                        "beats": [
                            {"notes": [{"string": 0, "fret": 5, "hp": True}], "duration": [1, 4]},
                            {
                                "notes": [
                                    {
                                        "string": 1,
                                        "fret": 7,
                                        "slide": "shift",
                                        "bend": {"points": []},
                                    }
                                ],
                                "duration": [1, 4],
                            },
                            {
                                "notes": [
                                    {"string": 2, "fret": 0, "dead": True},
                                    {
                                        "string": 3,
                                        "fret": 2,
                                        "ghost": True,
                                        "vibrato": True,
                                        "harmonic": {"type": "natural"},
                                    },
                                ],
                                "duration": [1, 4],
                                "palmMute": True,
                            },
                            {"notes": [{"rest": True}], "rest": True, "duration": [1, 4]},
                        ]
                    }
                ],
            },
            {
                "signature": [3, 4],
                "voices": [
                    {
                        "beats": [
                            {"notes": [{"string": 5, "fret": 3}], "duration": [1, 4]},
                            {"notes": [{"string": 5, "fret": 3}], "duration": [1, 4]},
                            {"notes": [{"string": 5, "fret": 3}], "duration": [1, 4]},
                        ]
                    }
                ],
            },
        ],
    }
    tab = songsterr_to_tab(meta, [(2, TrackJson.model_validate(raw))], None)
    t = tab.tracks[0]
    beats = t.measures[0].voices[0].beats
    assert "hammer" in beats[0].notes[0].tech
    assert {"slide", "bend"} <= set(beats[1].notes[0].tech)
    assert beats[2].notes[0].dead and beats[2].notes[0].pitch_midi is None
    assert {"vibrato", "harmonic", "palm_mute"} <= set(beats[2].notes[1].tech)
    assert beats[2].notes[1].ghost
    assert beats[3].is_rest
    assert tab.tempo_bpm == 120
    assert t.measures[1].voices[0].beats[1].tempo_bpm == 140
    assert t.measures[1].time_signature is not None
    assert t.measures[1].time_signature.numerator == 3
    assert t.measures[0].time_signature is not None  # first measure carries the initial ts
    assert validate_tab(tab) == []


def test_conversion_fails_on_invalid_notes(meta: Meta) -> None:
    raw = {
        "tuning": [64, 59, 55, 50, 45, 40],
        "measures": [
            {
                "voices": [
                    {
                        "beats": [
                            {"notes": [{"string": 9, "fret": 1}], "duration": [1, 4]},
                        ]
                    }
                ]
            }
        ],
    }
    # out-of-range strings are dropped with a warning rather than failing
    tab = songsterr_to_tab(meta, [(0, TrackJson.model_validate(raw))], None)
    assert tab.warnings and "dropped note" in tab.warnings[0]
    with pytest.raises(ConversionError):
        songsterr_to_tab(meta, [], None)
