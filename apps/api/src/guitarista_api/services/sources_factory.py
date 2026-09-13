"""Build the ordered list of tab sources for the tier runner.

Later phases drop in ``sources/ultimate_guitar.py::UltimateGuitarSource`` and
``sources/audio.py::AudioSource``; the imports below are guarded so this module keeps working
until those files exist, and the order here *is* the fallback order.
"""

from __future__ import annotations

import importlib
from typing import Any

import structlog

from guitarista_api.settings import Settings
from guitarista_api.sources.base import TabSource
from guitarista_api.sources.songsterr import SongsterrSource

log = structlog.get_logger(__name__)


def _optional_source(module: str, name: str) -> type[Any] | None:
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return None
    return getattr(mod, name, None)


def build_sources(settings: Settings, **kwargs: Any) -> list[TabSource]:
    """Ordered tiers: Songsterr -> Ultimate Guitar -> Audio. ``kwargs`` are passed to optional
    sources that accept them (e.g. ``ml_sidecar=``), ignored otherwise."""
    sources: list[TabSource] = [SongsterrSource()]

    # Phase 4: UltimateGuitarSource (HTML search + embedded-store page parser), behind enable_ug.
    if settings.enable_ug:
        ug_cls = _optional_source("guitarista_api.sources.ultimate_guitar", "UltimateGuitarSource")
        if ug_cls is not None:
            sources.append(_construct(ug_cls, kwargs))

    # Phase 5: AudioSource(upload | yt-dlp -> demucs? -> basic-pitch -> solver), always last.
    if settings.enable_audio_tier:
        audio_cls = _optional_source("guitarista_api.sources.audio", "AudioSource")
        if audio_cls is not None:
            sources.append(_construct(audio_cls, kwargs))

    log.info("sources.built", tiers=[s.name for s in sources])
    return sources


def _construct(cls: type[Any], kwargs: dict[str, Any]) -> Any:
    try:
        return cls(**kwargs)
    except TypeError:
        return cls()


def tier_timeouts(settings: Settings) -> dict[str, float]:
    return {
        "songsterr": settings.tier_timeout_songsterr,
        "ultimate_guitar": settings.tier_timeout_ug,
        "audio": settings.tier_timeout_audio,
    }
