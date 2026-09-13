"""Tier 3: audio (upload or yt-dlp) -> ML sidecar -> solver. Last resort, confidence <= 0.5.

Browsing exposes a single pseudo-candidate ``external_id="audio"`` whose ``available``/``reason``
mirror ``can_handle`` for the song's latest audio upload (or yt-dlp when none exists).
"""

from __future__ import annotations

from typing import Any

from guitarista_api.adapters.ffmpeg import INSTALL_HINT as FFMPEG_HINT
from guitarista_api.adapters.ffmpeg import ffmpeg_available
from guitarista_api.adapters.ml_sidecar import SETUP_HINT, MLSidecar
from guitarista_api.adapters.ytdlp import INSTALL_HINT as YTDLP_HINT
from guitarista_api.adapters.ytdlp import ytdlp_available
from guitarista_api.db.repo import JobRepo
from guitarista_api.domain.candidate import Candidate
from guitarista_api.domain.enums import TierName
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.audio_pipeline import AudioPipeline
from guitarista_api.settings import Settings
from guitarista_api.sources.base import SourceError, SourceResult, all_excluded_error

AUDIO_CANDIDATE_ID = "audio"
AUDIO_SCORE = 0.5
"""Audio transcription confidence never exceeds 0.5; listed after every scraped candidate."""


class AudioSource:
    name: TierName = "audio"
    deterministic = False

    def __init__(self, ml_sidecar: MLSidecar | None = None, **_: Any) -> None:
        self._sidecar = ml_sidecar

    def sidecar_for(self, settings: Settings) -> MLSidecar:
        if self._sidecar is None:
            self._sidecar = MLSidecar.from_settings(settings)
        return self._sidecar

    def can_handle(
        self, request: TabRequest, song: Song, ctx: SourceContext
    ) -> tuple[bool, str | None]:
        settings = ctx.settings
        if not settings.enable_audio_tier:
            return False, "audio tier disabled (GUITARISTA_ENABLE_AUDIO_TIER=false)"
        if not request.upload_id:
            # Both a pasted audio_url and a search download through yt-dlp, so both need the flag.
            if not settings.enable_ytdlp:
                return False, (
                    "downloading audio with yt-dlp is disabled "
                    "(set GUITARISTA_ENABLE_YTDLP=true or upload audio)"
                    if request.audio_url
                    else "no audio upload and yt-dlp fetching is disabled "
                    "(set GUITARISTA_ENABLE_YTDLP=true, pass audio_url, or upload audio)"
                )
            if not ytdlp_available(settings.ytdlp_bin):
                return False, f"yt-dlp binary {settings.ytdlp_bin!r} not found; {YTDLP_HINT}"
        if not ffmpeg_available(settings.ffmpeg_bin):
            return False, f"ffmpeg binary {settings.ffmpeg_bin!r} not found; {FFMPEG_HINT}"
        sidecar = self.sidecar_for(settings)
        if sidecar.probed:
            reason = _sidecar_problem(sidecar)
            if reason:
                return False, reason
        # Not probed yet: let fetch() probe (async) and fail with the same message.
        return True, None

    async def candidates(self, song: Song, ctx: SourceContext, *, limit: int) -> list[Candidate]:
        async with ctx.session_factory() as session:
            upload_id = await JobRepo(session).latest_upload_for_song(song.id)
        probe = TabRequest(song_id=song.id, upload_id=upload_id)
        available, reason = self.can_handle(probe, song, ctx)
        return [
            Candidate(
                source="audio",
                external_id=AUDIO_CANDIDATE_ID,
                title=song.title,
                artist=song.artist,
                score=AUDIO_SCORE,
                kind=f"Upload {upload_id}" if upload_id else "YouTube (search)",
                available=available,
                reason=reason,
            )
        ]

    async def fetch(self, request: TabRequest, song: Song, ctx: SourceContext) -> SourceResult:
        if AUDIO_CANDIDATE_ID in request.excluded_ids(self.name):
            raise all_excluded_error(1, {"excluded": 1})
        sidecar = self.sidecar_for(ctx.settings)
        await sidecar.probe()
        reason = _sidecar_problem(sidecar)
        if reason:
            raise SourceError(reason)
        result = await AudioPipeline(sidecar).run_detailed(request, song, ctx)
        return SourceResult(tab=result.tab, detail=result.detail, message=result.message)


def _sidecar_problem(sidecar: MLSidecar) -> str | None:
    caps = sidecar.capabilities
    if caps is None:
        why = sidecar.probe_error or "unknown error"
        return f"ML sidecar unavailable ({why}); {SETUP_HINT}"
    if not caps.basic_pitch:
        return f"ML sidecar has no basic-pitch backend; {SETUP_HINT}"
    return None
