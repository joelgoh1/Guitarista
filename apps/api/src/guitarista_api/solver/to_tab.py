from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from guitarista_api.domain.enums import TabSourceKind
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
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent, ChordFretting

_POWERS = [Fraction(1, 2**k) for k in range(0, 9)]  # whole .. 1/256


def duration_from_fraction(value: Fraction) -> tuple[Duration, str | None]:
    """Convert a whole-note fraction into a Duration, detecting dots and 3:2 tuplets.

    Returns the duration and an optional warning when the value had to be approximated.
    """
    if value <= 0:
        raise ValueError("duration must be positive")
    for base in _POWERS:
        if value == base:
            return Duration(num=1, den=base.denominator), None
        if value == base * Fraction(3, 2):
            return Duration(num=1, den=base.denominator, dots=1), None
        if value == base * Fraction(7, 4):
            return Duration(num=1, den=base.denominator, dots=2), None
        if value == base * Fraction(2, 3):
            return Duration(num=1, den=base.denominator, tuplet=(3, 2)), None
    nearest = min(_POWERS, key=lambda b: abs(b - value))
    warning = f"duration {value} approximated as 1/{nearest.denominator}"
    return Duration(num=1, den=nearest.denominator), warning


def split_duration(value: Fraction) -> list[Fraction]:
    """Greedy split of an arbitrary fraction into exactly representable note values."""
    parts: list[Fraction] = []
    remaining = value
    while remaining > 0:
        chunk = _largest_exact(remaining)
        parts.append(chunk)
        remaining -= chunk
    return parts


def _largest_exact(value: Fraction) -> Fraction:
    for base in _POWERS:
        for mult in (Fraction(7, 4), Fraction(3, 2), Fraction(1)):
            candidate = base * mult
            if candidate <= value and duration_from_fraction(candidate)[1] is None:
                return candidate
    return _POWERS[-1] if value >= _POWERS[-1] else value


def build_tab(
    chords: Sequence[ChordEvent],
    frettings: Sequence[ChordFretting],
    cfg: StringConfig,
    *,
    tempo_bpm: float,
    time_signature: TimeSignature,
    title: str,
    artist: str | None = None,
    source: TabSourceKind = TabSourceKind.MANUAL,
    source_ref: str | None = None,
    warnings: Sequence[str] = (),
    track_name: str = "Guitar",
) -> Tab:
    """Pack fretted chord events into measures, splitting notes across barlines with ties."""
    if len(chords) != len(frettings):
        raise ValueError("chords and frettings must be index-aligned")
    packer = _Packer(cfg, time_signature)
    for chord, fretting in zip(chords, frettings, strict=True):
        packer.add(chord, fretting)
    measures, pack_warnings = packer.finish()
    track = Track(name=track_name, tuning=list(cfg.tuning), capo=cfg.capo, measures=measures)
    return Tab(
        title=title,
        artist=artist,
        source=source,
        source_ref=source_ref,
        tempo_bpm=tempo_bpm,
        time_signature=time_signature,
        tracks=[track],
        warnings=[*warnings, *pack_warnings],
    )


class _Packer:
    def __init__(self, cfg: StringConfig, ts: TimeSignature) -> None:
        self.cfg = cfg
        self.measure_len = ts.measure_length()
        self.ts = ts
        self.measures: list[Measure] = []
        self.current: list[Beat] = []
        self.filled = Fraction(0)
        self.warnings: list[str] = []

    def add(self, chord: ChordEvent, fretting: ChordFretting) -> None:
        remaining = chord.duration
        first = True
        while remaining > 0:
            room = self.measure_len - self.filled
            chunk = min(remaining, room)
            for piece in split_duration(chunk):
                self.current.append(self._beat(chord, fretting, piece, tie=not first))
                self.filled += piece
                first = False
            remaining -= chunk
            if self.filled >= self.measure_len:
                self._close_measure()

    def _beat(self, chord: ChordEvent, fretting: ChordFretting, value: Fraction, tie: bool) -> Beat:
        duration, warning = duration_from_fraction(value)
        if warning:
            self.warnings.append(f"event {chord.index}: {warning}")
        notes = [
            Note(
                string=n.string,
                fret=n.fret,
                pitch_midi=self.cfg.pitch_at(n.string, n.fret),
                tie=tie,
            )
            for n in fretting.notes
        ]
        return Beat(
            duration=duration,
            notes=notes,
            chord_name=chord.meta.get("chord_name"),
            text=chord.meta.get("text"),
            tempo_bpm=chord.meta.get("tempo_bpm"),
        )

    def _close_measure(self) -> None:
        number = len(self.measures) + 1
        ts = self.ts if number == 1 else None
        self.measures.append(
            Measure(number=number, time_signature=ts, voices=[Voice(beats=self.current)])
        )
        self.current = []
        self.filled = Fraction(0)

    def finish(self) -> tuple[list[Measure], list[str]]:
        if self.current:
            rest = self.measure_len - self.filled
            if rest > 0:
                for piece in split_duration(rest):
                    self.current.append(Beat(duration=duration_from_fraction(piece)[0]))
                self.warnings.append(f"measure {len(self.measures) + 1}: padded with rests")
            self._close_measure()
        return self.measures, self.warnings
