"""Songsterr (unofficial API) adapter: HTTP client, lenient schemas, conversion to ``Tab``."""

from guitarista_api.adapters.songsterr.client import SongsterrClient, SongsterrError
from guitarista_api.adapters.songsterr.convert import (
    ConversionError,
    eligible_track_indices,
    songsterr_to_tab,
)

__all__ = [
    "ConversionError",
    "SongsterrClient",
    "SongsterrError",
    "eligible_track_indices",
    "songsterr_to_tab",
]
