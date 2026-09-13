from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from functools import cached_property
from typing import Any


@dataclass(frozen=True, slots=True)
class ChordEvent:
    """One simultaneous group of pitches (or a rest when ``pitches`` is empty)."""

    pitches: tuple[int, ...]
    duration: Fraction = Fraction(1, 4)
    index: int = 0
    meta: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pitches", tuple(sorted(self.pitches)))

    @property
    def is_rest(self) -> bool:
        return not self.pitches


@dataclass(frozen=True, slots=True, order=True)
class NoteFretting:
    string: int
    fret: int
    muted: bool = False

    @property
    def is_open(self) -> bool:
        return self.fret == 0


@dataclass(frozen=True)
class ChordFretting:
    """A fretting for a whole chord; ``notes`` are kept sorted by string."""

    notes: tuple[NoteFretting, ...]
    hint_misses: int = field(default=0, compare=False, hash=False)
    """Notes whose (string, fret) disagrees with a model hint on the chord (see candidates)."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(sorted(self.notes, key=lambda n: n.string)))

    @classmethod
    def rest(cls) -> ChordFretting:
        return cls(())

    def is_rest(self) -> bool:
        return not self.notes

    @cached_property
    def frets_pressed(self) -> tuple[int, ...]:
        return tuple(n.fret for n in self.notes if n.fret > 0 and not n.muted)

    @cached_property
    def all_open(self) -> bool:
        return not self.frets_pressed

    @cached_property
    def fret_span(self) -> int:
        if not self.frets_pressed:
            return 0
        return max(self.frets_pressed) - min(self.frets_pressed)

    @cached_property
    def mean_fret(self) -> float:
        """Mean of pressed frets; 0.0 when nothing is pressed (rest or all open)."""
        if not self.frets_pressed:
            return 0.0
        return sum(self.frets_pressed) / len(self.frets_pressed)

    @cached_property
    def mean_string(self) -> float:
        if not self.notes:
            return 0.0
        return sum(n.string for n in self.notes) / len(self.notes)

    @cached_property
    def hand_position(self) -> int:
        """Lowest pressed fret (index-finger position); 0 for open/rest."""
        return min(self.frets_pressed) if self.frets_pressed else 0

    @cached_property
    def finger_count(self) -> int:
        """Barre-aware: distinct pressed frets."""
        return len(set(self.frets_pressed))

    def skipped_strings(self) -> int:
        strings = [n.string for n in self.notes]
        if not strings:
            return 0
        return max(strings) - min(strings) + 1 - len(strings)

    def string_sum(self) -> int:
        return sum(n.string for n in self.notes)

    def __str__(self) -> str:
        return " ".join(f"{n.fret}.{n.string}" for n in self.notes) or "r"
