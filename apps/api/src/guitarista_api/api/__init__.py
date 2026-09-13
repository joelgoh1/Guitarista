from __future__ import annotations

from fastapi import APIRouter

from guitarista_api.api import (
    health,
    jobs,
    recommendations,
    score,
    songs,
    spotify,
    tabs,
    uploads,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(uploads.router)
router.include_router(score.router)
router.include_router(songs.router)
router.include_router(jobs.router)
router.include_router(tabs.router)
router.include_router(spotify.router)
router.include_router(recommendations.router)

__all__ = ["router"]
