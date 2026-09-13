from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from guitarista_api import __version__
from guitarista_api.adapters.http import make_http_client
from guitarista_api.adapters.llm import OpenRouterLLM
from guitarista_api.adapters.ml_sidecar import MLSidecar
from guitarista_api.adapters.spotify import SpotifyClient
from guitarista_api.adapters.spotify_user import SpotifyUserClient
from guitarista_api.api import router
from guitarista_api.db.repo import JobRepo
from guitarista_api.db.session import create_all, make_engine, make_session_factory
from guitarista_api.errors import install_error_handlers
from guitarista_api.jobs.manager import JobManager
from guitarista_api.jobs.prefetch import NoodlePrefetcher
from guitarista_api.services.sources_factory import build_sources
from guitarista_api.settings import Settings, get_settings

log = structlog.get_logger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        settings.work_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.db_url)
        await create_all(engine)
        session_factory = make_session_factory(engine)
        http = make_http_client()
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.http = http
        app.state.spotify = (
            SpotifyClient(http, settings.spotify_client_id, settings.spotify_client_secret)
            if settings.spotify_enabled
            else None
        )
        # Noodle mode: acts as the signed-in user (PKCE, client id only, tokens in SQLite).
        # Built whenever a client id is set; it reads the auth row lazily on first use.
        app.state.spotify_user = (
            SpotifyUserClient(http, settings.spotify_client_id, session_factory)
            if settings.spotify_user_enabled
            else None
        )
        app.state.spotify_pkce = {}
        # Optional LLM assist (OpenRouter); every source keeps a deterministic path without it.
        app.state.llm = (
            OpenRouterLLM(
                http,
                settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
            )
            if settings.llm_enabled
            else None
        )
        # Phase 5: ML sidecar handle shared by the audio tier and /health; probed in the
        # background so startup never blocks on `uv run`.
        ml_sidecar = MLSidecar.from_settings(settings)
        app.state.ml_sidecar = ml_sidecar
        if settings.enable_audio_tier:
            ml_sidecar.start_probe()
        app.state.sources = build_sources(settings, ml_sidecar=ml_sidecar)
        app.state.job_manager = JobManager(session_factory)
        # Noodle prefetch: always constructed so /spotify/callback can start it the moment the
        # user connects; it only runs while a grant is stored.
        prefetcher: NoodlePrefetcher | None = None
        if settings.noodle_enabled and app.state.spotify_user is not None:
            prefetcher = NoodlePrefetcher(
                settings=settings,
                session_factory=session_factory,
                manager=app.state.job_manager,
                http=http,
                sources=app.state.sources,
                spotify_user=app.state.spotify_user,
                spotify=app.state.spotify,
                llm=app.state.llm,
            )
            if await app.state.spotify_user.is_connected():
                prefetcher.start()
        app.state.noodle_prefetcher = prefetcher
        app.state.noodle_refresh_lock = asyncio.Lock()
        async with session_factory() as session:
            interrupted = await JobRepo(session).mark_interrupted()
        if interrupted:
            log.warning("jobs.interrupted_on_boot", count=interrupted)
        log.info("api.started", version=__version__, db=settings.db_url)
        try:
            yield
        finally:
            if prefetcher is not None:
                await prefetcher.stop()
            await app.state.job_manager.shutdown()
            await ml_sidecar.close()
            await http.aclose()
            await engine.dispose()

    app = FastAPI(title="Guitarista API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("guitarista_api.main:app", host="127.0.0.1", port=8000, reload=True)
