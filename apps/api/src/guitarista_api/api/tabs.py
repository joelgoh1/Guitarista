from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from guitarista_api.db.repo import TabRepo
from guitarista_api.deps import SessionDep
from guitarista_api.domain.tab import Tab
from guitarista_api.errors import NotFound, UnprocessableError
from guitarista_api.services.export import tab_to_alphatex, tab_to_ascii, tab_to_musicxml

router = APIRouter(prefix="/tabs", tags=["tabs"])

TabFormat = Literal["json", "alphatex", "musicxml", "ascii"]

_MEDIA = {
    "alphatex": "text/x-alphatex; charset=utf-8",
    "ascii": "text/plain; charset=utf-8",
    "musicxml": "application/vnd.recordare.musicxml+xml; charset=utf-8",
}


class TabSummary(BaseModel):
    id: str
    title: str
    artist: str | None
    source: str
    confidence: float
    created_at: datetime
    song_id: str | None = None
    track_count: int


@router.get("", response_model=list[TabSummary])
async def list_tabs(
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    song_id: str | None = Query(default=None, description="Only tabs for this song"),
) -> list:
    return await TabRepo(session).list_summaries(limit, song_id)


@router.get(
    "/{tab_id}",
    response_model=Tab,
    responses={200: {"content": {"text/x-alphatex": {}, "text/plain": {}}}},
)
async def get_tab(
    tab_id: str,
    session: SessionDep,
    format: TabFormat = "json",
    track: int = Query(default=0, ge=0),
) -> Tab | Response:
    tab = await TabRepo(session).get(tab_id)
    if tab is None:
        raise NotFound(f"tab {tab_id!r} not found")
    if track >= len(tab.tracks):
        raise UnprocessableError(f"track {track} out of range (tab has {len(tab.tracks)})")
    if format == "json":
        return tab
    exporters = {"alphatex": tab_to_alphatex, "musicxml": tab_to_musicxml, "ascii": tab_to_ascii}
    return Response(exporters[format](tab, track), media_type=_MEDIA[format])
