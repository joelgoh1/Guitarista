from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.llm import LLMClient
from guitarista_api.adapters.spotify import SpotifyClient
from guitarista_api.adapters.spotify_user import SpotifyUserClient
from guitarista_api.jobs.manager import JobManager
from guitarista_api.settings import Settings, get_settings


def settings_dep(request: Request) -> Settings:
    """Settings the app was created with (falls back to env settings outside a lifespan)."""
    state_settings: Settings | None = getattr(request.app.state, "settings", None)
    return state_settings or get_settings()


def session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = session_factory(request)
    async with factory() as session:
        yield session


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def spotify_client(request: Request) -> SpotifyClient | None:
    return getattr(request.app.state, "spotify", None)


def spotify_user_client(request: Request) -> SpotifyUserClient | None:
    return getattr(request.app.state, "spotify_user", None)


def llm_client(request: Request) -> LLMClient | None:
    return getattr(request.app.state, "llm", None)


SettingsDep = Annotated[Settings, Depends(settings_dep)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(session_factory)]
HttpDep = Annotated[httpx.AsyncClient, Depends(http_client)]
JobManagerDep = Annotated[JobManager, Depends(job_manager)]
SpotifyDep = Annotated[SpotifyClient | None, Depends(spotify_client)]
SpotifyUserDep = Annotated[SpotifyUserClient | None, Depends(spotify_user_client)]
LLMDep = Annotated[LLMClient | None, Depends(llm_client)]
