from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent, ChordFretting, NoteFretting


class NoValidFretting(Exception):
    def __init__(self, chord: ChordEvent, cfg: StringConfig, reason: str = "") -> None:
        self.chord = chord
        self.cfg = cfg
        msg = f"no fretting for pitches {list(chord.pitches)} at event {chord.index}"
        super().__init__(f"{msg}: {reason}" if reason else msg)


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    max_fret: int = 15
    max_fret_span: int = 4
    max_fingers: int = 4


DEFAULT_CANDIDATE_CONFIG = CandidateConfig()


def enumerate_frettings(
    chord: ChordEvent, cfg: StringConfig, ccfg: CandidateConfig = DEFAULT_CANDIDATE_CONFIG
) -> list[ChordFretting]:
    """All playable frettings for ``chord``, filtered by span/finger limits.

    Falls back to the unfiltered set if the filter removes everything, and raises
    :class:`NoValidFretting` if no fretting exists at all.
    """
    if chord.is_rest:
        return [ChordFretting.rest()]
    per_pitch = [cfg.frettings_for(p, ccfg.max_fret) for p in chord.pitches]
    for pitch, options in zip(chord.pitches, per_pitch, strict=True):
        if not options:
            raise NoValidFretting(chord, cfg, f"pitch {pitch} not reachable within fret range")
    if len(chord.pitches) > cfg.num_strings:
        raise NoValidFretting(chord, cfg, "more pitches than strings")

    unfiltered = _combine(per_pitch, chord.pitches, chord.meta.get("hints"))
    if not unfiltered:
        raise NoValidFretting(chord, cfg, "pitches need the same string")
    filtered = [f for f in unfiltered if _is_playable(f, ccfg)]
    return filtered or unfiltered


def _combine(
    per_pitch: list[list[tuple[int, int]]],
    pitches: tuple[int, ...],
    hints: dict[int, tuple[int, int]] | None,
) -> list[ChordFretting]:
    """Cartesian product of per-pitch options; ``hints`` (pitch → (string, fret)) count misses."""
    out: list[ChordFretting] = []
    seen: set[tuple[NoteFretting, ...]] = set()
    for combo in product(*per_pitch):
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue
        misses = 0
        if hints:
            misses = sum(
                1
                for p, sf in zip(pitches, combo, strict=True)
                if p in hints and tuple(hints[p]) != sf
            )
        fretting = ChordFretting(tuple(NoteFretting(s, f) for s, f in combo), hint_misses=misses)
        if fretting.notes not in seen:
            seen.add(fretting.notes)
            out.append(fretting)
    return out


def _is_playable(fretting: ChordFretting, ccfg: CandidateConfig) -> bool:
    return fretting.fret_span <= ccfg.max_fret_span and fretting.finger_count <= ccfg.max_fingers
