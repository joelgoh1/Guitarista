from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed ``GUITARISTA_``."""

    model_config = SettingsConfigDict(
        env_prefix="GUITARISTA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = Path("./data")
    db_url: str = "sqlite+aiosqlite:///./data/guitarista.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    log_level: str = "INFO"

    enable_songsterr: bool = True
    enable_ug: bool = True
    enable_audio_tier: bool = True
    enable_ytdlp: bool = False
    enable_separation: bool = False
    tier_timeout_songsterr: float = 20
    tier_timeout_ug: float = 30
    tier_timeout_audio: float = 900

    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/v1/spotify/callback"
    """Must match the Spotify dashboard exactly; Spotify only accepts literal loopback IPs."""
    web_base_url: str = "http://localhost:3000"
    """Where the OAuth callback bounces the browser back to."""

    noodle_enabled: bool = True
    noodle_prefetch_target: int = 5
    noodle_refresh_hours: float = 6

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "qwen/qwen3.8-flash"
    llm_timeout: float = 30

    ml_cmd: str = "uv run --directory ../ml guitarista-ml"
    audio_model: Literal["basic-pitch", "tabcnn"] = "basic-pitch"
    """Transcriber for the audio tier; tabcnn also predicts string/fret (needs shipped weights)."""
    ml_models_dir: Path = Path("./data/models")
    demucs_model: str = "htdemucs_6s"
    ffmpeg_bin: str = "ffmpeg"
    ytdlp_bin: str = "yt-dlp"
    mscore_bin: str = "mscore"
    score_convert_timeout: float = 60

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    @property
    def spotify_user_enabled(self) -> bool:
        """PKCE login only needs the client id (no secret)."""
        return bool(self.spotify_client_id)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    def tier_timeout(self, tier: str, default: float = 60.0) -> float:
        return float(getattr(self, f"tier_timeout_{tier}", default))


@lru_cache
def get_settings() -> Settings:
    return Settings()
