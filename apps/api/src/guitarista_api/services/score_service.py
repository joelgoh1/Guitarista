from __future__ import annotations

from pathlib import Path

import structlog

from guitarista_api.adapters.score_import import score_to_chord_events
from guitarista_api.domain.enums import TabSourceKind
from guitarista_api.domain.tab import Tab
from guitarista_api.solver.candidates import CandidateConfig
from guitarista_api.solver.cost import CostProfile, cost_for_profile
from guitarista_api.solver.instrument import TUNINGS, StringConfig
from guitarista_api.solver.search import OutOfRange, solve
from guitarista_api.solver.to_tab import build_tab

log = structlog.get_logger(__name__)


def score_file_to_tab(
    path: Path,
    *,
    part_index: int = 0,
    tuning: list[int] | None = None,
    capo: int = 0,
    max_fret: int = 15,
    out_of_range: OutOfRange = "raise",
    cost_profile: CostProfile = "tabgen",
    source_ref: str | None = None,
    fallback_title: str = "Untitled",
) -> Tab:
    """Full score → tab pipeline: import, solve, pack. Raises NoValidFretting/UnsupportedScore."""
    chords, meta = score_to_chord_events(path, part_index)
    cfg = StringConfig(tuple(tuning) if tuning else TUNINGS["standard"], num_frets=24, capo=capo)
    result = solve(
        chords,
        cfg,
        cost=cost_for_profile(cost_profile),
        ccfg=CandidateConfig(max_fret=max_fret),
        out_of_range=out_of_range,
    )
    tab = build_tab(
        result.chords,
        result.frettings,
        cfg,
        tempo_bpm=meta.tempo_bpm,
        time_signature=meta.time_signature,
        title=meta.title or fallback_title,
        artist=meta.artist,
        source=TabSourceKind.SCORE,
        source_ref=source_ref,
        warnings=result.warnings,
    )
    log.info("score.solved", events=len(chords), cost=round(result.total_cost, 3), tab_id=tab.id)
    return tab
