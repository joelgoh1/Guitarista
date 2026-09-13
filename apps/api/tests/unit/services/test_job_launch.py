from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.domain.job import Job, TabRequest
from guitarista_api.domain.song import SongQuery
from guitarista_api.errors import UnprocessableError
from guitarista_api.services.job_launch import launch_tab_job
from guitarista_api.settings import Settings


class FakeManager:
    """Records ``submit`` calls without ever starting the job task."""

    def __init__(self) -> None:
        self.submitted: list[Job] = []
        self.factories: list[Callable[[], Awaitable[None]]] = []

    async def submit(self, job: Job, coro_factory: Callable[[], Awaitable[None]]) -> Job:
        self.submitted.append(job)
        self.factories.append(coro_factory)
        return job


@pytest.fixture
async def env(
    tmp_path: Path,
) -> AsyncIterator[tuple[Settings, async_sessionmaker[AsyncSession], httpx.AsyncClient]]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    async with httpx.AsyncClient() as http:
        yield settings, factory, http
    await engine.dispose()


async def _launch(env, body: TabRequest, manager: FakeManager) -> Job:
    settings, factory, http = env
    return await launch_tab_job(
        body=body,
        settings=settings,
        manager=manager,  # type: ignore[arg-type]
        http=http,
        session_factory=factory,
        spotify=None,
        llm=None,
        sources=[],
    )


async def test_rejects_empty_request(env) -> None:
    manager = FakeManager()
    with pytest.raises(UnprocessableError):
        await _launch(env, TabRequest(), manager)
    assert manager.submitted == []


async def test_submits_job_with_request_and_origin(env) -> None:
    manager = FakeManager()
    body = TabRequest(song=SongQuery(raw="oasis wonderwall"), origin="noodle")
    job = await _launch(env, body, manager)
    assert job.status == "queued"
    assert job.request is body
    assert job.request.origin == "noodle"
    assert manager.submitted == [job] and callable(manager.factories[0])


async def test_origin_defaults_to_user() -> None:
    assert TabRequest(song=SongQuery(raw="x")).origin == "user"
