from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from guitarista_api.solver.model import ChordFretting

CostProfile = Literal["tabgen", "lead", "beginner"]


class CostFunction(Protocol):
    """Additive cost model: ``local`` for a fretting on its own, ``transition`` between two."""

    def local(self, fretting: ChordFretting) -> float: ...

    def transition(self, prev: ChordFretting, cur: ChordFretting) -> float: ...


@dataclass(frozen=True, slots=True)
class BaselineWeights:
    """Weights for the tabgen-derived heuristics. All costs are >= 0 except the open bonus."""

    move: float = 1.0
    move_fret: float = 0.5
    steady: float = 0.3
    skipped_strings: float = 0.5
    high_fret: float = 0.08
    open_string_bonus: float = -0.2
    string_change: float = 0.15
    position_shift: float = 1.0
    position_shift_tolerance: int = 4
    minkowski_order: int = 2
    hint_mismatch: float = 3.0
    """Per-note cost for ignoring a (string, fret) hint from a string-aware transcriber (TabCNN).

    About the price of a three-fret position jump, so a hint wins over ordinary hand movement
    but a hint that forces a big leap or an awkward shape can still be overruled.
    """
    open_move: float = 0.0
    """Per-fret cost of switching between an all-open fretting and a fretted hand position.

    tabgen treats open notes as free of movement, which makes lead lines bounce between an open
    string and a high position; charging the distance to the nut keeps them in position.
    """


COST_PROFILES: dict[CostProfile, BaselineWeights] = {
    "tabgen": BaselineWeights(),
    "lead": BaselineWeights(open_move=0.6, open_string_bonus=-0.1),
    "beginner": BaselineWeights(open_string_bonus=-0.4, high_fret=0.15),
}


def cost_for_profile(profile: CostProfile) -> BaselineCost:
    return BaselineCost(COST_PROFILES[profile])


def _minkowski(dx: float, dy: float, order: int) -> float:
    return (abs(dx) ** order + abs(dy) ** order) ** (1.0 / order)


class BaselineCost:
    """Port of the tabgen baseline heuristics (see tabgen/modelling.py)."""

    def __init__(self, weights: BaselineWeights | None = None) -> None:
        self.w = weights or BaselineWeights()

    def local(self, f: ChordFretting) -> float:
        if f.is_rest():
            return 0.0
        w = self.w
        cost = w.steady * self._steady_spread(f)
        cost += w.skipped_strings * f.skipped_strings()
        cost += w.high_fret * f.mean_fret
        cost += w.open_string_bonus * sum(1 for n in f.notes if n.is_open)
        cost += w.hint_mismatch * f.hint_misses
        return cost

    def transition(self, prev: ChordFretting, cur: ChordFretting) -> float:
        if prev.is_rest() or cur.is_rest():
            return 0.0
        if prev.notes == cur.notes:
            return 0.0
        w = self.w
        cost = w.move * self._move_distance(prev, cur)
        cost += w.move_fret * self._move_fret(prev, cur)
        if len(prev.notes) == 1 and len(cur.notes) == 1:
            cost += w.string_change * abs(prev.notes[0].string - cur.notes[0].string)
        if not prev.all_open and not cur.all_open:
            shift = abs(prev.hand_position - cur.hand_position)
            if shift > w.position_shift_tolerance:
                cost += w.position_shift
        if w.open_move and prev.all_open != cur.all_open:
            fretted = prev if cur.all_open else cur
            cost += w.open_move * fretted.hand_position
        return cost

    @staticmethod
    def _steady_spread(f: ChordFretting) -> float:
        pressed = [n for n in f.notes if n.fret > 0]
        total = 0.0
        for i, a in enumerate(pressed):
            for b in pressed[i + 1 :]:
                total += _minkowski(a.fret - b.fret, a.string - b.string, 2)
        return total

    def _move_distance(self, prev: ChordFretting, cur: ChordFretting) -> float:
        # tabgen: no fret movement cost when either side is open/rest (mean_fret == 0)
        if prev.all_open or cur.all_open:
            return 0.0
        return _minkowski(
            cur.mean_fret - prev.mean_fret,
            cur.mean_string - prev.mean_string,
            self.w.minkowski_order,
        )

    @staticmethod
    def _move_fret(prev: ChordFretting, cur: ChordFretting) -> float:
        if prev.all_open or cur.all_open:
            return 0.0
        return abs(cur.mean_fret - prev.mean_fret)
