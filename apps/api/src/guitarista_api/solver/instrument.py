from __future__ import annotations

from dataclasses import dataclass
from typing import Self

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

TUNINGS: dict[str, tuple[int, ...]] = {
    # string 1 (highest) .. string N (lowest), MIDI pitches
    "standard": (64, 59, 55, 50, 45, 40),
    "drop_d": (64, 59, 55, 50, 45, 38),
    "half_down": (63, 58, 54, 49, 44, 39),
    "dadgad": (62, 57, 55, 50, 45, 38),
    "open_g": (62, 59, 55, 50, 43, 38),
    "bass_4": (43, 38, 33, 28),
    "ukulele": (69, 64, 60, 67),
}


def midi_to_name(pitch: int) -> str:
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


@dataclass(frozen=True, slots=True)
class StringConfig:
    """Instrument description. ``tuning`` lists open-string MIDI pitches, string 1 first."""

    tuning: tuple[int, ...] = TUNINGS["standard"]
    num_frets: int = 24
    capo: int = 0

    def __post_init__(self) -> None:
        if not self.tuning:
            raise ValueError("tuning must have at least one string")
        if self.num_frets < 0 or self.capo < 0:
            raise ValueError("num_frets and capo must be non-negative")

    @classmethod
    def from_name(cls, name: str, *, num_frets: int = 24, capo: int = 0) -> Self:
        try:
            return cls(TUNINGS[name], num_frets, capo)
        except KeyError as exc:
            raise KeyError(f"unknown tuning {name!r}; known: {sorted(TUNINGS)}") from exc

    @property
    def num_strings(self) -> int:
        return len(self.tuning)

    @property
    def strings(self) -> range:
        return range(1, self.num_strings + 1)

    def open_pitch(self, string: int) -> int:
        """Sounding pitch of the open string (capo included)."""
        self._check_string(string)
        return self.tuning[string - 1] + self.capo

    def pitch_at(self, string: int, fret: int) -> int:
        if fret < 0 or fret > self.num_frets:
            raise ValueError(f"fret {fret} outside 0..{self.num_frets}")
        return self.open_pitch(string) + fret

    def frettings_for(self, pitch: int, max_fret: int | None = None) -> list[tuple[int, int]]:
        """All ``(string, fret)`` pairs sounding ``pitch``, string 1 first."""
        limit = self.num_frets if max_fret is None else min(max_fret, self.num_frets)
        out: list[tuple[int, int]] = []
        for string in self.strings:
            fret = pitch - self.open_pitch(string)
            if 0 <= fret <= limit:
                out.append((string, fret))
        return out

    def pitch_range(self, max_fret: int | None = None) -> tuple[int, int]:
        limit = self.num_frets if max_fret is None else min(max_fret, self.num_frets)
        return min(self.tuning) + self.capo, max(self.tuning) + self.capo + limit

    def reference_table(self, max_fret: int | None = None) -> dict[int, list[tuple[int, int]]]:
        lo, hi = self.pitch_range(max_fret)
        return {p: self.frettings_for(p, max_fret) for p in range(lo, hi + 1)}

    def check_consistency(self, string: int, fret: int, pitch: int) -> bool:
        return self.pitch_at(string, fret) == pitch

    def _check_string(self, string: int) -> None:
        if not 1 <= string <= self.num_strings:
            raise ValueError(f"string {string} outside 1..{self.num_strings}")
