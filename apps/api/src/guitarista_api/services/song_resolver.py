"""Turn a ``SongQuery`` (link / typed text / title+artist) into a persisted ``Song``.

Spotify path (when credentials are configured): a pasted link is looked up directly; typed text
is searched and the top hit taken. Raw path (always available): parse ``"artist - title"``,
``"title by artist"`` or a plain string (title only, artist empty). Songs are deduped in SQLite on
``spotify_id`` / ``isrc`` / ``normalized_query`` so repeat jobs share one song row.
"""

from __future__ import annotations

import hashlib
import re

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from guitarista_api.adapters.spotify import SpotifyClient, SpotifyError, parse_spotify_track_id
from guitarista_api.db.repo import SongRepo
from guitarista_api.domain.song import Song, SongQuery
from guitarista_api.services.normalize import normalize_title, normalized_query

log = structlog.get_logger(__name__)

_BY_RE = re.compile(r"^(?P<title>.+?)\s+by\s+(?P<artist>.+)$", re.IGNORECASE)
_DASH_RE = re.compile(r"^(?P<artist>.+?)\s+[-–—]\s+(?P<title>.+)$")


class SongResolveError(Exception):
    """User-facing resolution failure (empty query, bad link, Spotify unavailable...)."""


def parse_raw_query(raw: str) -> tuple[str, str]:
    """Return ``(title, artist)``; artist is ``""`` for a plain string."""
    text = re.sub(r"\s+", " ", raw).strip()
    if not text:
        raise SongResolveError("empty query")
    if (m := _DASH_RE.match(text)) is not None:
        return normalize_title(m.group("title")), m.group("artist").strip()
    if (m := _BY_RE.match(text)) is not None:
        return normalize_title(m.group("title")), m.group("artist").strip()
    return normalize_title(text), ""


def raw_song(title: str, artist: str) -> Song:
    key = normalized_query(title, artist)
    digest = hashlib.sha1(key.encode()).hexdigest()[:24]
    return Song(id=f"raw_{digest}", title=title, artist=artist, normalized_query=key)


class SongResolver:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        spotify: SpotifyClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.spotify = spotify

    async def resolve(self, query: SongQuery) -> Song:
        if query.is_empty():
            raise SongResolveError("provide a Spotify link, a search string, or a title")
        song = await self._resolve_fresh(query)
        return await self._dedupe_and_store(song)

    async def by_id(self, song_id: str) -> Song:
        """An already resolved song (``TabRequest.song_id``); unknown ids are a resolve error."""
        async with self.session_factory() as session:
            song = await SongRepo(session).get(song_id)
        if song is None:
            raise SongResolveError(f"song {song_id!r} not found; resolve it first")
        return song

    async def _resolve_fresh(self, query: SongQuery) -> Song:
        link_id = parse_spotify_track_id(query.spotify_url) or parse_spotify_track_id(query.raw)
        if link_id:
            if self.spotify is None:
                raise SongResolveError(
                    "Spotify links need GUITARISTA_SPOTIFY_CLIENT_ID/SECRET configured; "
                    "type the artist and title instead"
                )
            return await self._spotify_track(link_id)
        if query.spotify_url and query.spotify_url.strip():
            raise SongResolveError("that does not look like a Spotify track link")

        if query.title and query.title.strip():
            title, artist = normalize_title(query.title), (query.artist or "").strip()
        else:
            title, artist = parse_raw_query(query.raw or "")

        if self.spotify is not None:
            found = await self._spotify_search(title, artist)
            if found is not None:
                return found
        return raw_song(title, artist)

    async def _spotify_track(self, track_id: str) -> Song:
        assert self.spotify is not None
        try:
            return (await self.spotify.track(track_id)).to_song()
        except SpotifyError as exc:
            raise SongResolveError(f"could not load that Spotify track: {exc}") from exc

    async def _spotify_search(self, title: str, artist: str) -> Song | None:
        assert self.spotify is not None
        try:
            hits = await self.spotify.search(title, artist or None, limit=1)
        except SpotifyError as exc:
            log.warning("spotify.search_failed", error=str(exc))
            return None
        return hits[0].to_song() if hits else None

    async def _dedupe_and_store(self, song: Song) -> Song:
        async with self.session_factory() as session:
            repo = SongRepo(session)
            existing = await repo.find_match(
                spotify_id=song.spotify_id,
                isrc=song.isrc,
                normalized_query=song.normalized_query,
            )
            if existing is not None:
                # Prefer richer metadata (Spotify over raw) but keep the existing id.
                merged = (
                    song.model_copy(update={"id": existing.id}) if song.spotify_id else existing
                )
                if merged is not existing:
                    await repo.upsert(merged)
                return merged
            await repo.upsert(song)
            return song
