from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from guitarista_api.db.models import JobRow, SongRow, TabRow, UploadRow
from guitarista_api.domain.job import Job
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import Tab


class TabRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def add(self, tab: Tab) -> None:
        self.s.add(
            TabRow(
                id=tab.id,
                song_id=tab.song_id,
                title=tab.title,
                artist=tab.artist,
                source=str(tab.source),
                confidence=tab.confidence,
                payload=tab.model_dump(mode="json"),
                created_at=tab.created_at,
            )
        )
        await self.s.commit()

    async def get(self, tab_id: str) -> Tab | None:
        row = await self.s.get(TabRow, tab_id)
        return Tab.model_validate(row.payload) if row else None

    async def list_refs_for_song(self, song_id: str) -> list[tuple[str, str, str | None]]:
        """``(tab_id, source, source_ref)`` for every tab of ``song_id``, newest first."""
        stmt = select(TabRow).where(TabRow.song_id == song_id).order_by(TabRow.created_at.desc())
        rows = (await self.s.execute(stmt)).scalars().all()
        return [(r.id, r.source, r.payload.get("source_ref")) for r in rows]

    async def list_summaries(
        self, limit: int = 100, song_id: str | None = None
    ) -> list[dict[str, Any]]:
        stmt = select(TabRow).order_by(TabRow.created_at.desc()).limit(limit)
        if song_id is not None:
            stmt = stmt.where(TabRow.song_id == song_id)
        rows = (await self.s.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "artist": r.artist,
                "source": r.source,
                "confidence": r.confidence,
                "created_at": r.created_at,
                "song_id": r.song_id,
                "track_count": len(r.payload.get("tracks", [])),
            }
            for r in rows
        ]


class UploadRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def add(self, row: UploadRow) -> None:
        self.s.add(row)
        await self.s.commit()

    async def get(self, upload_id: str) -> UploadRow | None:
        return await self.s.get(UploadRow, upload_id)


class JobRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def upsert(self, job: Job) -> None:
        row = await self.s.get(JobRow, job.id)
        payload = job.model_dump(mode="json")
        if row is None:
            self.s.add(
                JobRow(
                    id=job.id,
                    status=job.status,
                    song_id=job.song_id,
                    tab_id=job.tab_id,
                    payload=payload,
                    created_at=job.created_at,
                )
            )
        else:
            row.status, row.song_id, row.tab_id, row.payload = (
                job.status,
                job.song_id,
                job.tab_id,
                payload,
            )
        await self.s.commit()

    async def get(self, job_id: str) -> Job | None:
        row = await self.s.get(JobRow, job_id)
        return Job.model_validate(row.payload) if row else None

    async def list(self, limit: int = 100, status: str | None = None) -> list[Job]:
        stmt = select(JobRow).order_by(JobRow.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(JobRow.status == status)
        rows = (await self.s.execute(stmt)).scalars().all()
        return [Job.model_validate(r.payload) for r in rows]

    async def latest_upload_for_song(self, song_id: str) -> str | None:
        """``upload_id`` of the newest job for ``song_id`` that carried an audio upload."""
        stmt = (
            select(JobRow)
            .where(JobRow.song_id == song_id)
            .where(JobRow.payload["request"]["upload_id"].as_string().is_not(None))
            .order_by(JobRow.created_at.desc())
            .limit(1)
        )
        row = (await self.s.execute(stmt)).scalars().first()
        if row is None:
            return None
        upload_id = row.payload.get("request", {}).get("upload_id")
        return str(upload_id) if upload_id else None

    async def mark_interrupted(self) -> int:
        """Flag jobs left ``queued``/``running`` by a previous process as ``interrupted``."""
        stmt = select(JobRow).where(JobRow.status.in_(["queued", "running"]))
        rows = (await self.s.execute(stmt)).scalars().all()
        for row in rows:
            payload = dict(row.payload)
            payload["status"] = "interrupted"
            payload["error"] = payload.get("error") or "server restarted while the job was running"
            row.status, row.payload = "interrupted", payload
        await self.s.commit()
        return len(rows)


class SongRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def upsert(self, song: Song) -> None:
        row = await self.s.get(SongRow, song.id)
        if row is None:
            self.s.add(
                SongRow(
                    id=song.id,
                    title=song.title,
                    artist=song.artist,
                    payload=song.model_dump(mode="json"),
                )
            )
        else:
            row.title, row.artist, row.payload = (
                song.title,
                song.artist,
                song.model_dump(mode="json"),
            )
        await self.s.commit()

    async def get(self, song_id: str) -> Song | None:
        row = await self.s.get(SongRow, song_id)
        return Song.model_validate(row.payload) if row else None

    async def find_match(
        self,
        *,
        spotify_id: str | None = None,
        isrc: str | None = None,
        normalized_query: str | None = None,
    ) -> Song | None:
        """First song matching spotify_id, then isrc, then normalized_query (JSON payload)."""
        for key, value in (
            ("spotify_id", spotify_id),
            ("isrc", isrc),
            ("normalized_query", normalized_query),
        ):
            if not value:
                continue
            stmt = (
                select(SongRow)
                .where(SongRow.payload[key].as_string() == value)
                .order_by(SongRow.created_at)
                .limit(1)
            )
            row = (await self.s.execute(stmt)).scalars().first()
            if row is not None:
                return Song.model_validate(row.payload)
        return None
