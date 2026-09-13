from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from guitarista_api.adapters.score_import import UnsupportedScore
from guitarista_api.db.repo import TabRepo, UploadRepo
from guitarista_api.deps import SessionDep
from guitarista_api.domain.tab import Tab
from guitarista_api.errors import NotFound, UnprocessableError
from guitarista_api.services.score_service import score_file_to_tab
from guitarista_api.solver.candidates import NoValidFretting
from guitarista_api.solver.cost import CostProfile
from guitarista_api.solver.search import OutOfRange

router = APIRouter(prefix="/score", tags=["score"])


class ScoreTabRequest(BaseModel):
    upload_id: str
    part_index: int = Field(default=0, ge=0)
    tuning: list[int] | None = Field(default=None, min_length=1, max_length=12)
    capo: int = Field(default=0, ge=0, le=12)
    max_fret: int = Field(default=15, ge=3, le=24)
    out_of_range: OutOfRange = "raise"
    cost_profile: CostProfile = Field(
        default="tabgen",
        description=(
            "'tabgen' classic heuristics, 'lead' stays in position instead of jumping to open "
            "strings, 'beginner' favours open strings and low frets"
        ),
    )


@router.post("/tab", response_model=Tab, status_code=201)
async def score_to_tab(body: ScoreTabRequest, session: SessionDep) -> Tab:
    upload = await UploadRepo(session).get(body.upload_id)
    if upload is None or upload.kind != "score":
        raise NotFound(f"score upload {body.upload_id!r} not found")
    path = Path(upload.path)
    try:
        tab = await run_in_threadpool(
            score_file_to_tab,
            path,
            part_index=body.part_index,
            tuning=body.tuning,
            capo=body.capo,
            max_fret=body.max_fret,
            out_of_range=body.out_of_range,
            cost_profile=body.cost_profile,
            source_ref=body.upload_id,
            fallback_title=Path(upload.filename).stem,
        )
    except FileNotFoundError as exc:
        raise NotFound(f"file for upload {body.upload_id!r} is missing on disk") from exc
    except NoValidFretting as exc:
        hint = "Try out_of_range='octave_shift' or 'drop', another tuning, or a higher max_fret."
        raise UnprocessableError(f"{exc}. {hint}") from exc
    except UnsupportedScore as exc:
        raise UnprocessableError(str(exc)) from exc
    await TabRepo(session).add(tab)
    return tab
