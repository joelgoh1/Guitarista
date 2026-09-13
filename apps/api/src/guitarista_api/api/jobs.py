from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from guitarista_api.db.repo import JobRepo
from guitarista_api.deps import (
    HttpDep,
    JobManagerDep,
    LLMDep,
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    SpotifyDep,
)
from guitarista_api.domain.enums import JobStatus
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.errors import NotFound
from guitarista_api.services.job_launch import launch_tab_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=Job, status_code=201)
async def create_job(
    body: TabRequest,
    request: Request,
    settings: SettingsDep,
    manager: JobManagerDep,
    http: HttpDep,
    session_factory: SessionFactoryDep,
    spotify: SpotifyDep,
    llm: LLMDep,
) -> Job:
    """Start a song→tab job. Poll ``GET /jobs/{id}`` or stream ``GET /jobs/{id}/events``."""
    return await launch_tab_job(
        body=body,
        settings=settings,
        manager=manager,
        http=http,
        session_factory=session_factory,
        spotify=spotify,
        llm=llm,
        sources=request.app.state.sources,
    )


@router.get("", response_model=list[Job])
async def list_jobs(
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=500),
    status: JobStatus | None = None,
) -> list[Job]:
    return await JobRepo(session).list(limit, status)


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str, manager: JobManagerDep) -> Job:
    job = await manager.get(job_id)
    if job is None:
        raise NotFound(f"job {job_id!r} not found")
    return job


@router.post("/{job_id}/cancel", response_model=Job)
async def cancel_job(job_id: str, manager: JobManagerDep) -> Job:
    job = await manager.get(job_id)
    if job is None:
        raise NotFound(f"job {job_id!r} not found")
    if await manager.cancel(job_id):
        # Let the task observe the cancellation and persist its final state.
        for _ in range(50):
            job = await manager.get(job_id) or job
            if job.status in {"cancelled", "done", "failed"}:
                break
            await asyncio.sleep(0.02)
    return job


@router.get(
    "/{job_id}/events",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
)
async def job_events(job_id: str, request: Request, manager: JobManagerDep) -> EventSourceResponse:
    """Server-sent events: replays the tier log, then streams ``tier``/``progress``/``done``/
    ``error`` events; a final ``end`` event closes the stream. Data is JSON (see ``JobEvent``)."""
    if await manager.get(job_id) is None:
        raise NotFound(f"job {job_id!r} not found")

    async def gen() -> AsyncIterator[dict[str, Any]]:
        async for event in manager.subscribe(job_id):
            if await request.is_disconnected():
                return
            yield {
                "event": event.type,
                "id": event.at.isoformat(),
                "data": json.dumps(event.payload, default=str),
            }
        yield {"event": "end", "data": json.dumps({"job_id": job_id})}

    return EventSourceResponse(gen())
