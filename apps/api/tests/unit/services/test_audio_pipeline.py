from __future__ import annotations

import json
from pathlib import Path

from guitarista_api.adapters.ml_sidecar import parse_transcription
from guitarista_api.domain.enums import TabSourceKind
from guitarista_api.domain.tab import TimeSignature
from guitarista_api.solver.candidates import CandidateConfig
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.quantize import estimate_grid, quantize
from guitarista_api.solver.search import solve
from guitarista_api.solver.to_tab import build_tab

FIXTURE_RESULT = {
    "notes": [
        {"onset_s": 0.0, "offset_s": 0.9, "pitch_midi": 40, "velocity": 0.8, "confidence": None},
        {"onset_s": 1.0, "offset_s": 1.9, "pitch_midi": 45, "velocity": 0.7, "confidence": None},
        {"onset_s": 2.0, "offset_s": 2.9, "pitch_midi": 50, "velocity": 0.9, "confidence": None},
    ],
    "tempo_bpm": 60.0,
    "duration_s": 3.0,
    "stem": "mix",
    "model": "fake",
}


def test_fixture_result_quantizes_and_solves_to_open_strings(tmp_path: Path) -> None:
    result = parse_transcription(json.loads(json.dumps(FIXTURE_RESULT)))
    grid = estimate_grid(result.notes, result.tempo_bpm)
    assert grid.tempo_bpm == 60.0
    chords = quantize(result.notes, grid)
    assert [c.pitches for c in chords] == [(40,), (45,), (50,)]
    cfg = StringConfig()
    solved = solve(chords, cfg, ccfg=CandidateConfig(max_fret=15), out_of_range="octave_shift")
    picks = {(n.string, n.fret) for f in solved.frettings for n in f.notes}
    assert picks == {(6, 0), (5, 0), (4, 0)}  # canonical: string 6 = low E
    tab = build_tab(
        solved.chords,
        solved.frettings,
        cfg,
        tempo_bpm=grid.tempo_bpm,
        time_signature=TimeSignature(),
        title="t",
        source=TabSourceKind.AUDIO,
    )
    notes = [n for m in tab.tracks[0].measures for v in m.voices for b in v.beats for n in b.notes]
    assert [(n.string, n.fret, n.pitch_midi) for n in notes] == [(6, 0, 40), (5, 0, 45), (4, 0, 50)]
    assert tab.tracks[0].measures[0].voices[0].beats[-1].is_rest  # padded to a full 4/4 bar


def test_octave_shift_for_out_of_range_pitches() -> None:
    result = parse_transcription(
        {"notes": [{"onset_s": 0, "offset_s": 0.5, "pitch_midi": 28, "velocity": 0.5}]}
    )
    chords = quantize(result.notes, estimate_grid(result.notes, 120))
    solved = solve(chords, StringConfig(), out_of_range="octave_shift")
    assert solved.chords[0].pitches == (40,) and solved.warnings
