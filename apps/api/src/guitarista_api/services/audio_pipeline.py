"""Tier 3: audio -> tab.

acquire (upload | yt-dlp) -> ffmpeg mono 22.05 kHz wav -> [demucs guitar stem] -> basic-pitch
transcription -> quantize -> fretting solver -> ``Tab``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from guitarista_api.adapters.ffmpeg import FfmpegError, to_wav_mono
from guitarista_api.adapters.ml_sidecar import MLSidecar, SidecarError, TranscribeParams
from guitarista_api.adapters.ytdlp import YtCandidate, YtdlpError, fetch_audio, search_candidates
from guitarista_api.db.repo import UploadRepo
from guitarista_api.domain.enums import TabSourceKind
from guitarista_api.domain.job import TabRequest
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import Tab, TimeSignature
from guitarista_api.domain.transcription import TranscriptionResult
from guitarista_api.jobs.context import SourceContext
from guitarista_api.services.yt_match import pick_best, rejection_message
from guitarista_api.solver.candidates import CandidateConfig, NoValidFretting
from guitarista_api.solver.cost import cost_for_profile
from guitarista_api.solver.instrument import TUNINGS, StringConfig
from guitarista_api.solver.quantize import estimate_grid, quantize
from guitarista_api.solver.search import solve
from guitarista_api.solver.to_tab import build_tab
from guitarista_api.sources.base import SourceError

log = structlog.get_logger(__name__)

SEARCH_LIMIT = 5
"""How many YouTube hits to score before picking; metadata-only, so this is cheap."""
TARGET_SR = 22050
FMIN_HZ = 80.0
FMAX_HZ = 1300.0
GUITAR_STEM = "guitar"
MIX_WARNING = (
    "transcribed from the full mix; enable GUITARISTA_ENABLE_SEPARATION to isolate the guitar first"
)

# Progress budget per stage (start, end) within the tier's 0..1.
_P_ACQUIRE = (0.0, 0.10)
_P_CONVERT = (0.10, 0.15)
_P_SEPARATE = (0.15, 0.50)
_P_TRANSCRIBE = (0.50, 0.90)
_P_SOLVE = (0.90, 1.0)


@dataclass(slots=True)
class AudioPipelineResult:
    tab: Tab
    detail: dict[str, Any] = field(default_factory=dict)
    message: str = ""


class AudioPipeline:
    def __init__(self, sidecar: MLSidecar) -> None:
        self.sidecar = sidecar
        self._separation_requested = False

    async def run(self, request: TabRequest, song: Song, ctx: SourceContext) -> Tab:
        return (await self.run_detailed(request, song, ctx)).tab

    async def run_detailed(
        self, request: TabRequest, song: Song, ctx: SourceContext
    ) -> AudioPipelineResult:
        settings = ctx.settings
        detail: dict[str, Any] = {"llm_used": False}
        warnings: list[str] = []
        work = ctx.work_dir / "audio"
        work.mkdir(parents=True, exist_ok=True)

        # 1. acquire
        await ctx.progress(_P_ACQUIRE[0], "audio: acquiring")
        src, source_ref = await self._acquire(request, song, ctx, work, detail)

        # 2. convert
        await ctx.progress(_P_CONVERT[0], "audio: converting to wav")
        wav = work / "mix.wav"
        try:
            await to_wav_mono(src, wav, sr=TARGET_SR, ffmpeg_bin=settings.ffmpeg_bin)
        except FfmpegError as exc:
            raise SourceError(f"audio conversion failed: {exc}", detail) from exc

        # 3. optional separation
        stem_used = "mix"
        target = wav
        self._separation_requested = settings.enable_separation
        if settings.enable_separation:
            caps = await self.sidecar.probe()
            if caps is not None and caps.demucs:
                stem = await self._separate(wav, work, ctx, warnings)
                if stem is not None:
                    target, stem_used = stem, GUITAR_STEM
            else:
                warnings.append(
                    "source separation requested but Demucs is not installed "
                    "(run `uv sync --extra separate` in apps/ml); using the full mix"
                )
        detail["stem"] = stem_used

        # 4. transcribe
        await ctx.progress(_P_TRANSCRIBE[0], "audio: transcribing")
        result = await self._transcribe(target, work, ctx, detail)
        if not result.notes:
            raise SourceError("no notes detected in the audio", detail)

        # 5. quantize -> solve -> tab
        await ctx.progress(_P_SOLVE[0], "audio: solving frettings")
        tab = self._to_tab(request, song, result, source_ref, stem_used, warnings, detail)
        await ctx.progress(_P_SOLVE[1], "audio: done")
        message = (
            f"transcribed {len(result.notes)} notes from {stem_used} "
            f"({tab.tempo_bpm:g} bpm, confidence {tab.confidence:.2f})"
        )
        return AudioPipelineResult(tab=tab, detail=detail, message=message)

    # ----------------------------------------------------------------- stages

    async def _acquire(
        self,
        request: TabRequest,
        song: Song,
        ctx: SourceContext,
        work: Path,
        detail: dict[str, Any],
    ) -> tuple[Path, str]:
        settings = ctx.settings
        if request.upload_id:
            async with ctx.session_factory() as session:
                row = await UploadRepo(session).get(request.upload_id)
            if row is None:
                raise SourceError(f"upload {request.upload_id!r} not found", detail)
            if row.kind != "audio":
                raise SourceError(
                    f"upload {request.upload_id!r} is a {row.kind} upload, not audio", detail
                )
            path = Path(row.path)
            if not await asyncio.to_thread(path.exists):
                raise SourceError(f"upload file for {request.upload_id!r} is missing", detail)
            detail["input"] = {"kind": "upload", "upload_id": row.id, "filename": row.filename}
            return path, f"upload:{row.id}"
        if not settings.enable_ytdlp:
            raise SourceError(
                "no audio upload and yt-dlp fetching is disabled (GUITARISTA_ENABLE_YTDLP=false)",
                detail,
            )
        if request.audio_url:
            # Explicit user intent: download exactly this, no search and no match scoring.
            target, chosen = request.audio_url, None
            detail["input"] = {"kind": "ytdlp_url", "url": request.audio_url}
        else:
            chosen = await self._pick_video(song, ctx, detail)
            target = chosen.url
        await ctx.progress(_P_ACQUIRE[0] + 0.04, "audio: downloading with yt-dlp")
        try:
            path = await fetch_audio(
                target,
                work / "ytdlp",
                ytdlp_bin=settings.ytdlp_bin,
                ffmpeg_bin=settings.ffmpeg_bin,
            )
        except YtdlpError as exc:
            raise SourceError(f"yt-dlp download failed: {exc}", detail) from exc
        detail["input"]["file"] = path.name
        if chosen is not None:
            log.info(
                "audio.video_chosen",
                video_id=chosen.video_id,
                title=chosen.title,
                duration_s=chosen.duration_s,
            )
        return path, target

    async def _pick_video(
        self, song: Song, ctx: SourceContext, detail: dict[str, Any]
    ) -> YtCandidate:
        """Search YouTube and return the hit that matches ``song``, or raise ``SourceError``."""
        settings = ctx.settings
        query = song.normalized_query or f"{song.artist} {song.title}".strip()
        if not query:
            raise SourceError("nothing to search for on YouTube (no title)", detail)
        await ctx.progress(_P_ACQUIRE[0] + 0.02, "audio: searching YouTube")
        try:
            candidates = await search_candidates(
                query, limit=SEARCH_LIMIT, ytdlp_bin=settings.ytdlp_bin
            )
        except YtdlpError as exc:
            raise SourceError(f"yt-dlp search failed: {exc}", detail) from exc
        best, breakdowns = pick_best(song, candidates)
        detail["input"] = {
            "kind": "ytdlp",
            "query": query,
            "expected_duration_s": song.duration_s,
            "considered": breakdowns,
        }
        if best is None:
            raise SourceError(rejection_message(song, breakdowns), detail)
        detail["input"] |= {
            "video_id": best.video_id,
            "url": best.url,
            "title": best.title,
            "uploader": best.uploader,
            "duration_s": best.duration_s,
        }
        return best

    async def _separate(
        self, wav: Path, work: Path, ctx: SourceContext, warnings: list[str]
    ) -> Path | None:
        settings = ctx.settings
        await ctx.progress(_P_SEPARATE[0], f"audio: separating ({settings.demucs_model})")

        async def on_progress(value: float, stage: str) -> None:
            await ctx.progress(_lerp(_P_SEPARATE, value), f"audio: separating {stage}".rstrip())

        try:
            stems = await self.sidecar.separate(
                wav,
                work / "stems",
                model=settings.demucs_model,
                stems=(GUITAR_STEM,),
                on_progress=on_progress,
            )
        except SidecarError as exc:
            log.warning("audio.separation_failed", error=exc.message, type=exc.type)
            warnings.append(f"source separation failed ({exc.message}); using the full mix")
            return None
        stem = stems.get(GUITAR_STEM)
        if stem is None or not stem.exists():
            warnings.append("Demucs produced no guitar stem; using the full mix")
            return None
        return stem

    async def _transcribe(
        self, wav: Path, work: Path, ctx: SourceContext, detail: dict[str, Any]
    ) -> TranscriptionResult:
        async def on_progress(value: float, stage: str) -> None:
            await ctx.progress(_lerp(_P_TRANSCRIBE, value), f"audio: transcribing {stage}".rstrip())

        params = TranscribeParams(
            fmin=FMIN_HZ, fmax=FMAX_HZ, estimate_tempo=True, model=ctx.settings.audio_model
        )
        try:
            result = await self.sidecar.transcribe(
                wav, work / "transcription.json", params, on_progress=on_progress
            )
        except SidecarError as exc:
            raise SourceError(f"transcription failed: {exc.message}", detail) from exc
        detail["transcription"] = {
            "notes": len(result.notes),
            "tempo_bpm": result.tempo_bpm,
            "beats": len(result.beats_s),
            "string_hints": sum(1 for n in result.notes if n.hint is not None),
            "duration_s": result.duration_s,
            "model": result.model,
        }
        return result

    def _to_tab(
        self,
        request: TabRequest,
        song: Song,
        result: TranscriptionResult,
        source_ref: str,
        stem_used: str,
        warnings: list[str],
        detail: dict[str, Any],
    ) -> Tab:
        tuning = tuple(request.tuning) if request.tuning else TUNINGS["standard"]
        cfg = StringConfig(tuning=tuning, capo=request.capo)
        ccfg = CandidateConfig(max_fret=request.max_fret) if request.max_fret else CandidateConfig()
        grid = estimate_grid(result.notes, result.tempo_bpm, beats_s=result.beats_s)
        chords = quantize(result.notes, grid)
        try:
            solved = solve(
                chords,
                cfg,
                cost=cost_for_profile(request.cost_profile),
                ccfg=ccfg,
                out_of_range="octave_shift",
            )
        except NoValidFretting as exc:
            raise SourceError(f"could not fret the transcription: {exc}", detail) from exc

        if grid.beats_s:
            tempo_note = f"tempo estimated at {grid.tempo_bpm:g} bpm (aligned to tracked beats)"
        elif result.tempo_bpm:
            tempo_note = f"tempo estimated at {grid.tempo_bpm:g} bpm"
        else:
            tempo_note = f"tempo guessed from note spacing ({grid.tempo_bpm:g} bpm)"
        tab_warnings = [
            f"transcribed automatically from audio ({stem_used} stem); expect errors",
            tempo_note,
            *([MIX_WARNING] if stem_used == "mix" and not self._separation_requested else []),
            *warnings,
            *result.warnings,
            *solved.warnings,
        ]
        tab = build_tab(
            solved.chords,
            solved.frettings,
            cfg,
            tempo_bpm=grid.tempo_bpm,
            time_signature=TimeSignature(),
            title=song.title or "Untitled",
            artist=song.artist or None,
            source=TabSourceKind.AUDIO,
            source_ref=source_ref,
            warnings=tab_warnings,
        )
        tab.confidence = round(sum(n.confidence for n in result.notes) / len(result.notes), 4)
        hinted = [
            (c, f)
            for c, f in zip(solved.chords, solved.frettings, strict=True)
            if c.meta.get("hints")
        ]
        detail["solver"] = {
            "events": len(solved.chords),
            "rests": sum(1 for c in solved.chords if c.is_rest),
            "hinted_events": len(hinted),
            "hint_misses": sum(f.hint_misses for _, f in hinted),
            "total_cost": round(solved.total_cost, 3),
            "tempo_bpm": grid.tempo_bpm,
            "max_fret": ccfg.max_fret,
            "cost_profile": request.cost_profile,
        }
        return tab


def _lerp(span: tuple[float, float], value: float) -> float:
    lo, hi = span
    return lo + (hi - lo) * max(0.0, min(1.0, value))
