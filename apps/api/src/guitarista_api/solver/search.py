from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import structlog

from guitarista_api.solver.candidates import CandidateConfig, NoValidFretting, enumerate_frettings
from guitarista_api.solver.cost import BaselineCost, CostFunction
from guitarista_api.solver.instrument import StringConfig
from guitarista_api.solver.model import ChordEvent, ChordFretting

log = structlog.get_logger(__name__)

Algorithm = Literal["viterbi", "beam"]
OutOfRange = Literal["raise", "drop", "octave_shift"]


@dataclass(frozen=True, slots=True)
class PruningConfig:
    """Beam-search pruning: keep sequences within ``beam_width`` std devs of the best,
    then at most ``max_sequences``."""

    beam_width: float = 1.0
    max_sequences: int = 50


@dataclass(slots=True)
class SolveResult:
    frettings: list[ChordFretting]
    total_cost: float
    warnings: list[str] = field(default_factory=list)
    per_step_cost: list[float] = field(default_factory=list)
    chords: list[ChordEvent] = field(default_factory=list)
    """The (possibly range-adjusted) chords that ``frettings`` correspond to, index-aligned."""


def _tie_key(f: ChordFretting) -> tuple[float, int]:
    return (f.mean_fret, f.string_sum())


def _fit_range(
    chords: Sequence[ChordEvent], cfg: StringConfig, ccfg: CandidateConfig, policy: OutOfRange
) -> tuple[list[ChordEvent], list[str]]:
    lo, hi = cfg.pitch_range(ccfg.max_fret)
    out: list[ChordEvent] = []
    warnings: list[str] = []
    for chord in chords:
        bad = [p for p in chord.pitches if not lo <= p <= hi]
        if not bad:
            out.append(chord)
            continue
        if policy == "raise":
            raise NoValidFretting(chord, cfg, f"pitches {bad} outside range {lo}..{hi}")
        if policy == "drop":
            kept = tuple(p for p in chord.pitches if lo <= p <= hi)
            warnings.append(f"event {chord.index}: dropped out-of-range pitches {bad}")
        else:
            kept = tuple(sorted({_shift_into(p, lo, hi) for p in chord.pitches}))
            warnings.append(f"event {chord.index}: octave-shifted out-of-range pitches {bad}")
        out.append(ChordEvent(kept, chord.duration, chord.index, chord.meta))
    return out, warnings


def _make_frettable(
    chords: Sequence[ChordEvent], cfg: StringConfig, ccfg: CandidateConfig, warnings: list[str]
) -> list[ChordEvent]:
    """Drop pitches from chords no hand can play (string collisions, too many notes).

    Transcribers happily emit E2 + G#2 together, which both live on the low E string. The pitch
    with the fewest playable positions goes first (that is the one causing the collision), ties
    broken by lowest confidence when the chord carries its source notes, then highest pitch.
    """
    out: list[ChordEvent] = []
    for chord in chords:
        current = chord
        dropped: list[int] = []
        while True:
            try:
                enumerate_frettings(current, cfg, ccfg)
                break
            except NoValidFretting:
                if len(current.pitches) <= 1:
                    raise
                victim = _victim(current, cfg, ccfg)
                dropped.append(victim)
                current = ChordEvent(
                    tuple(p for p in current.pitches if p != victim),
                    current.duration,
                    current.index,
                    current.meta,
                )
        if dropped:
            warnings.append(f"event {chord.index}: dropped unplayable pitches {dropped}")
        out.append(current)
    return out


def _victim(chord: ChordEvent, cfg: StringConfig, ccfg: CandidateConfig) -> int:
    notes = chord.meta.get("source_notes") or []
    conf = {n.pitch_midi: (n.confidence, n.velocity) for n in notes}
    return min(
        chord.pitches,
        key=lambda p: (len(cfg.frettings_for(p, ccfg.max_fret)), conf.get(p, (1.0, 1.0)), -p),
    )


def _shift_into(pitch: int, lo: int, hi: int) -> int:
    while pitch < lo:
        pitch += 12
    while pitch > hi:
        pitch -= 12
    return pitch


def solve(
    chords: Sequence[ChordEvent],
    cfg: StringConfig,
    cost: CostFunction | None = None,
    pruning: PruningConfig | None = None,
    ccfg: CandidateConfig | None = None,
    algorithm: Algorithm = "viterbi",
    out_of_range: OutOfRange = "raise",
) -> SolveResult:
    """Find the minimum-cost fretting sequence for ``chords``.

    Rests carry the last non-rest fretting forward so transitions across rests still apply.
    """
    cost = cost or BaselineCost()
    ccfg = ccfg or CandidateConfig()
    pruning = pruning or PruningConfig()
    fitted, warnings = _fit_range(chords, cfg, ccfg, out_of_range)
    if out_of_range != "raise":
        fitted = _make_frettable(fitted, cfg, ccfg, warnings)
    if not fitted:
        return SolveResult([], 0.0, warnings, [], [])
    candidates = [enumerate_frettings(c, cfg, ccfg) for c in fitted]
    if algorithm == "viterbi":
        picks, costs = _viterbi(candidates, cost)
    else:
        picks, costs = _beam(candidates, cost, pruning)
    log.debug("solve.done", events=len(fitted), total_cost=sum(costs), algorithm=algorithm)
    return SolveResult(picks, sum(costs), warnings, costs, fitted)


def _context(prev_ctx: ChordFretting | None, f: ChordFretting) -> ChordFretting | None:
    """Rests keep the previous hand context."""
    return prev_ctx if f.is_rest() else f


def _step_cost(cost: CostFunction, ctx: ChordFretting | None, f: ChordFretting) -> float:
    local = cost.local(f)
    if ctx is None or f.is_rest():
        return local
    return local + cost.transition(ctx, f)


def _viterbi(
    candidates: list[list[ChordFretting]], cost: CostFunction
) -> tuple[list[ChordFretting], list[float]]:
    # state = index into candidates[t]; rests have a single candidate, context flows through
    n = len(candidates)
    best: list[list[float]] = []
    back: list[list[int]] = []
    ctx: list[list[ChordFretting | None]] = []

    first = candidates[0]
    best.append([cost.local(f) for f in first])
    back.append([-1] * len(first))
    ctx.append([_context(None, f) for f in first])

    for t in range(1, n):
        cur = candidates[t]
        row_cost: list[float] = []
        row_back: list[int] = []
        row_ctx: list[ChordFretting | None] = []
        for f in cur:
            j, total = _best_predecessor(best[t - 1], ctx[t - 1], candidates[t - 1], f, cost)
            row_cost.append(total)
            row_back.append(j)
            row_ctx.append(_context(ctx[t - 1][j], f))
        best.append(row_cost)
        back.append(row_back)
        ctx.append(row_ctx)

    last = _argmin(best[-1], candidates[-1])
    picks: list[ChordFretting] = []
    idx = last
    for t in range(n - 1, -1, -1):
        picks.append(candidates[t][idx])
        idx = back[t][idx]
    picks.reverse()
    step_costs = _recompute_costs(picks, cost)
    return picks, step_costs


def _best_predecessor(
    prev_costs: list[float],
    prev_ctx: list[ChordFretting | None],
    prev_cands: list[ChordFretting],
    f: ChordFretting,
    cost: CostFunction,
) -> tuple[int, float]:
    best_j, best_total = 0, math.inf
    for j, pc in enumerate(prev_costs):
        total = pc + _step_cost(cost, prev_ctx[j], f)
        if total < best_total - 1e-12 or (
            abs(total - best_total) <= 1e-12
            and _tie_key(prev_cands[j]) < _tie_key(prev_cands[best_j])
        ):
            best_j, best_total = j, total
    return best_j, best_total


def _argmin(costs: list[float], cands: list[ChordFretting]) -> int:
    order = sorted(range(len(costs)), key=lambda i: (round(costs[i], 9), _tie_key(cands[i])))
    return order[0]


def _recompute_costs(picks: list[ChordFretting], cost: CostFunction) -> list[float]:
    out: list[float] = []
    ctx: ChordFretting | None = None
    for f in picks:
        out.append(_step_cost(cost, ctx, f))
        ctx = _context(ctx, f)
    return out


@dataclass(slots=True)
class _Seq:
    picks: list[ChordFretting]
    cost: float
    ctx: ChordFretting | None


def _beam(
    candidates: list[list[ChordFretting]], cost: CostFunction, pruning: PruningConfig
) -> tuple[list[ChordFretting], list[float]]:
    """Port of tabgen's Solver.solve/_prune beam search over whole sequences."""
    seqs = [_Seq([f], cost.local(f), _context(None, f)) for f in candidates[0]]
    for cands in candidates[1:]:
        branched = [
            _Seq(s.picks + [f], s.cost + _step_cost(cost, s.ctx, f), _context(s.ctx, f))
            for s in seqs
            for f in cands
        ]
        seqs = _prune(branched, pruning)
    best = min(seqs, key=lambda s: (round(s.cost, 9), [_tie_key(f) for f in s.picks]))
    return best.picks, _recompute_costs(best.picks, cost)


def _prune(seqs: list[_Seq], pruning: PruningConfig) -> list[_Seq]:
    if len(seqs) <= 1:
        return seqs
    costs = [s.cost for s in seqs]
    mean = sum(costs) / len(costs)
    std = math.sqrt(sum((c - mean) ** 2 for c in costs) / len(costs))
    limit = min(costs) + std + pruning.beam_width * std
    kept = sorted(
        (s for s in seqs if s.cost <= limit),
        key=lambda s: (round(s.cost, 9), [_tie_key(f) for f in s.picks]),
    )
    if pruning.max_sequences > 0:
        kept = kept[: pruning.max_sequences]
    return kept
