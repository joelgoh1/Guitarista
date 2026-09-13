from __future__ import annotations

import pytest

from guitarista_api.solver.instrument import TUNINGS, StringConfig, midi_to_name


def test_standard_open_pitches() -> None:
    cfg = StringConfig()
    assert [cfg.open_pitch(s) for s in cfg.strings] == [64, 59, 55, 50, 45, 40]
    assert cfg.pitch_at(6, 5) == 45
    assert cfg.check_consistency(1, 3, 67)


def test_capo_shifts_everything() -> None:
    cfg = StringConfig(capo=2)
    assert cfg.open_pitch(6) == 42
    assert cfg.pitch_range(15) == (42, 81)


def test_from_name_and_unknown() -> None:
    assert StringConfig.from_name("drop_d").tuning == TUNINGS["drop_d"]
    with pytest.raises(KeyError):
        StringConfig.from_name("nope")


def test_reference_table_covers_range() -> None:
    cfg = StringConfig()
    table = cfg.reference_table(15)
    assert min(table) == 40 and max(table) == 79
    assert all(table[p] for p in table)


def test_midi_to_name() -> None:
    assert midi_to_name(64) == "E4" and midi_to_name(40) == "E2" and midi_to_name(61) == "C#4"
