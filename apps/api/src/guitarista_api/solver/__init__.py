"""Pure fretting solver: instrument model, candidate enumeration, cost, search, tab packing."""

from __future__ import annotations

from guitarista_api.solver.candidates import CandidateConfig, NoValidFretting, enumerate_frettings
from guitarista_api.solver.cost import BaselineCost, BaselineWeights, CostFunction
from guitarista_api.solver.instrument import TUNINGS, StringConfig
from guitarista_api.solver.model import ChordEvent, ChordFretting, NoteFretting
from guitarista_api.solver.quantize import Grid, estimate_grid, quantize
from guitarista_api.solver.search import PruningConfig, SolveResult, solve
from guitarista_api.solver.to_tab import build_tab

__all__ = [
    "TUNINGS",
    "BaselineCost",
    "BaselineWeights",
    "CandidateConfig",
    "ChordEvent",
    "ChordFretting",
    "CostFunction",
    "Grid",
    "NoValidFretting",
    "NoteFretting",
    "PruningConfig",
    "SolveResult",
    "StringConfig",
    "build_tab",
    "enumerate_frettings",
    "estimate_grid",
    "quantize",
    "solve",
]
