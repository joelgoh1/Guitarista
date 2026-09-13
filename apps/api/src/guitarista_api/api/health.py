from __future__ import annotations

import shutil

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from guitarista_api import __version__
from guitarista_api.adapters.ml_sidecar import MLSidecar
from guitarista_api.adapters.musescore import musescore_available
from guitarista_api.db.repos_noodle import SpotifyAuthRepo
from guitarista_api.deps import SettingsDep

router = APIRouter(tags=["health"])


class Features(BaseModel):
    spotify: bool
    spotify_user: bool = Field(
        default=False, description="Spotify client id configured, so PKCE login is possible"
    )
    spotify_connected: bool = Field(
        default=False, description="A Spotify user grant is stored (noodle mode can read history)"
    )
    llm: bool
    songsterr: bool
    ug: bool
    audio: bool
    ytdlp: bool
    separation: bool
    ml_sidecar_ok: bool = Field(
        default=False, description="guitarista-ml sidecar responds to `probe` with basic-pitch"
    )
    separation_available: bool = Field(
        default=False, description="Demucs installed in the sidecar (uv sync --extra separate)"
    )
    tabcnn_available: bool = Field(
        default=False,
        description="TabCNN ONNX weights present in the sidecar (string/fret transcription)",
    )
    audio_model: str = Field(default="basic-pitch", description="Transcriber the audio tier uses")
    jobs: bool = Field(default=True, description="POST /jobs + SSE job pipeline available")
    musescore: bool = Field(
        default=False,
        description="MuseScore binary found; enables .mscz / Guitar Pro / Capella score uploads",
    )


class Health(BaseModel):
    status: str
    version: str
    features: Features
    ffmpeg: bool
    ytdlp: bool = Field(default=False, description="yt-dlp binary found on PATH")
    tiers: list[str] = Field(default_factory=list, description="Tab sources in fallback order")
    running_jobs: int = 0


@router.get("/health", response_model=Health)
async def health(settings: SettingsDep, request: Request) -> Health:
    state = request.app.state
    sources = getattr(state, "sources", [])
    manager = getattr(state, "job_manager", None)
    sidecar: MLSidecar | None = getattr(state, "ml_sidecar", None)
    caps = await sidecar.probe() if sidecar is not None else None  # cached after first call
    spotify_connected = False
    factory = getattr(state, "session_factory", None)
    if factory is not None:
        async with factory() as session:
            spotify_connected = await SpotifyAuthRepo(session).get() is not None
    return Health(
        status="ok",
        version=__version__,
        features=Features(
            spotify=getattr(state, "spotify", None) is not None,
            spotify_user=settings.spotify_user_enabled,
            spotify_connected=spotify_connected,
            llm=getattr(state, "llm", None) is not None,
            songsterr=settings.enable_songsterr,
            ug=settings.enable_ug,
            audio=settings.enable_audio_tier,
            ytdlp=settings.enable_ytdlp,
            separation=settings.enable_separation,
            ml_sidecar_ok=caps is not None and caps.basic_pitch,
            separation_available=caps is not None and caps.demucs,
            tabcnn_available=caps is not None and caps.tabcnn,
            audio_model=settings.audio_model,
            musescore=musescore_available(settings.mscore_bin),
        ),
        ffmpeg=shutil.which(settings.ffmpeg_bin) is not None,
        ytdlp=shutil.which(settings.ytdlp_bin) is not None,
        tiers=[s.name for s in sources],
        running_jobs=len(manager.running_ids()) if manager else 0,
    )
