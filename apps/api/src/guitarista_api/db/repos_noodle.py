"""Repositories for noodle mode: the Spotify user grant and the listening pool."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from guitarista_api.db.models import PoolEntryRow, SpotifyAuthRow
from guitarista_api.domain.noodle import PoolEntry

AUTH_ID = "default"

PoolEntries = list[PoolEntry]
"""Alias so annotations after ``PoolRepo.list`` are not shadowed by the method name."""

#: Fields a refresh of the pool is allowed to overwrite; everything else (status, tab_id, ...)
#: belongs to the prefetcher / the user and is preserved.
_REFRESHABLE = ("title", "artist", "album", "artwork_url", "duration_ms", "evidence", "score")


def _now() -> datetime:
    return datetime.now(UTC)


class SpotifyAuthRepo:
    """Single-row store for the user's Spotify grant (tokens are rotated in place)."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def get(self) -> SpotifyAuthRow | None:
        return await self.s.get(SpotifyAuthRow, AUTH_ID)

    async def upsert(
        self,
        *,
        refresh_token: str | None = None,
        access_token: str | None = None,
        expires_at: datetime | None = None,
        scope: str | None = None,
        spotify_user_id: str | None = None,
        display_name: str | None = None,
    ) -> SpotifyAuthRow:
        """Create or update the grant. ``None`` fields leave the stored value untouched."""
        row = await self.s.get(SpotifyAuthRow, AUTH_ID)
        if row is None:
            if not refresh_token:
                raise ValueError("a refresh_token is required to create the Spotify grant")
            row = SpotifyAuthRow(id=AUTH_ID, refresh_token=refresh_token, created_at=_now())
            self.s.add(row)
        elif refresh_token:
            row.refresh_token = refresh_token
        if access_token is not None:
            row.access_token = access_token
        if expires_at is not None:
            row.expires_at = expires_at
        if scope is not None:
            row.scope = scope
        if spotify_user_id is not None:
            row.spotify_user_id = spotify_user_id
        if display_name is not None:
            row.display_name = display_name
        row.updated_at = _now()
        await self.s.commit()
        return row

    async def delete(self) -> bool:
        """Drop the grant; returns whether there was one."""
        row = await self.s.get(SpotifyAuthRow, AUTH_ID)
        if row is None:
            return False
        await self.s.delete(row)
        await self.s.commit()
        return True


class PoolRepo:
    """The listening pool. Refreshes never clobber prefetch state or a dismissal."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def upsert_many(self, entries: Iterable[PoolEntry]) -> int:
        """Insert new entries and refresh the metadata/score of existing ones.

        ``status``, ``availability``, ``candidate``, ``song_id``, ``tab_id`` and ``job_id`` of an
        existing row are preserved, so a ``ready`` or ``dismissed`` entry survives a refresh.
        """
        now = _now()
        count = 0
        for entry in entries:
            row = await self.s.get(PoolEntryRow, entry.spotify_id)
            payload = entry.model_dump(mode="json")
            if row is None:
                row = PoolEntryRow(
                    spotify_id=entry.spotify_id,
                    availability=entry.availability,
                    candidate=(
                        entry.candidate.model_dump(mode="json") if entry.candidate else None
                    ),
                    song_id=entry.song_id,
                    tab_id=entry.tab_id,
                    job_id=entry.job_id,
                    status=entry.status,
                    attempts=entry.attempts,
                    created_at=now,
                    **{k: payload[k] for k in _REFRESHABLE},
                )
                self.s.add(row)
            else:
                for key in _REFRESHABLE:
                    setattr(row, key, payload[key])
            row.refreshed_at = now
            row.updated_at = now
            count += 1
        await self.s.commit()
        return count

    async def list(self, statuses: Sequence[str] | None = None, limit: int = 50) -> list[PoolEntry]:
        """Entries with the given statuses, best score first."""
        stmt = select(PoolEntryRow).order_by(PoolEntryRow.score.desc()).limit(limit)
        if statuses:
            stmt = stmt.where(PoolEntryRow.status.in_(list(statuses)))
        rows = (await self.s.execute(stmt)).scalars().all()
        return [PoolEntry.from_row(r) for r in rows]

    async def get(self, spotify_id: str) -> PoolEntry | None:
        row = await self.s.get(PoolEntryRow, spotify_id)
        return PoolEntry.from_row(row) if row else None

    async def set_status(
        self,
        spotify_id: str,
        status: str,
        *,
        error: str | None = None,
        job_id: str | None = None,
        availability: str | None = None,
        candidate_json: dict | None = None,
        bump_attempts: bool = False,
    ) -> PoolEntry | None:
        row = await self.s.get(PoolEntryRow, spotify_id)
        if row is None:
            return None
        row.status = status
        row.error = error
        if job_id is not None:
            row.job_id = job_id
        if availability is not None:
            row.availability = availability
        if candidate_json is not None:
            row.candidate = candidate_json
        if bump_attempts:
            row.attempts = (row.attempts or 0) + 1
        row.updated_at = _now()
        await self.s.commit()
        return PoolEntry.from_row(row)

    async def mark_tab(
        self, spotify_id: str, *, tab_id: str, song_id: str | None = None
    ) -> PoolEntry | None:
        """Attach a finished tab and flip the entry to ``ready``."""
        row = await self.s.get(PoolEntryRow, spotify_id)
        if row is None:
            return None
        row.tab_id = tab_id
        if song_id is not None:
            row.song_id = song_id
        row.status = "ready"
        row.availability = "available"
        row.error = None
        row.updated_at = _now()
        await self.s.commit()
        return PoolEntry.from_row(row)

    async def next_prefetchable(self, n: int = 1, *, max_attempts: int = 2) -> PoolEntries:
        """Best-scoring ``available`` entries with no tab yet and attempts left."""
        stmt = (
            select(PoolEntryRow)
            .where(PoolEntryRow.availability == "available")
            .where(PoolEntryRow.status.in_(["new", "failed"]))
            .where(PoolEntryRow.tab_id.is_(None))
            .where(PoolEntryRow.attempts < max_attempts)
            .order_by(PoolEntryRow.score.desc())
            .limit(n)
        )
        rows = (await self.s.execute(stmt)).scalars().all()
        return [PoolEntry.from_row(r) for r in rows]

    async def dismiss(self, spotify_id: str) -> bool:
        row = await self.s.get(PoolEntryRow, spotify_id)
        if row is None:
            return False
        row.status = "dismissed"
        row.updated_at = _now()
        await self.s.commit()
        return True

    async def newest_refresh(self) -> datetime | None:
        """``refreshed_at`` of the freshest entry, used to decide whether a rebuild is due."""
        stmt = select(PoolEntryRow.refreshed_at).order_by(PoolEntryRow.refreshed_at.desc()).limit(1)
        return (await self.s.execute(stmt)).scalars().first()

    async def clear(self) -> None:
        await self.s.execute(delete(PoolEntryRow))
        await self.s.commit()
