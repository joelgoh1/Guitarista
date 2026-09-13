from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import APIRouter, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from guitarista_api.adapters.ffmpeg import FfmpegError, probe_audio
from guitarista_api.adapters.musescore import MuseScoreError, to_musicxml
from guitarista_api.adapters.score_import import (
    ALL_SCORE_SUFFIXES,
    MUSESCORE_SUFFIXES,
    ScorePart,
    UnsupportedScore,
    parse_score,
)
from guitarista_api.db.models import UploadRow
from guitarista_api.db.repo import UploadRepo
from guitarista_api.deps import SessionDep, SettingsDep
from guitarista_api.errors import UnprocessableError

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_SCORE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 50 * 1024 * 1024
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

#: ``.mscz`` and the modern Guitar Pro / Capella containers are all zip archives; ``.mscx`` is
#: bare XML. Checking here turns a renamed file into a clear 422 instead of an mscore failure.
_ZIP_SUFFIXES = {".mscz", ".gp", ".gpx", ".capx"}


def _looks_plausible(suffix: str, head: bytes) -> bool:
    if suffix in _ZIP_SUFFIXES:
        return head.startswith(b"PK")
    if suffix == ".mscx":
        return head.lstrip()[:1] == b"<"
    return True  # .gp3/.gp4/.gp5/.cap are bespoke binary formats; let MuseScore judge them


class ScoreUploadResponse(BaseModel):
    upload_id: str
    filename: str
    title: str | None = None
    artist: str | None = None
    parts: list[ScorePart]


@router.post("/score", response_model=ScoreUploadResponse, status_code=201)
async def upload_score(
    file: UploadFile, session: SessionDep, settings: SettingsDep
) -> ScoreUploadResponse:
    filename = Path(file.filename or "score.musicxml").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALL_SCORE_SUFFIXES:
        raise UnprocessableError(
            f"unsupported file type {suffix!r}; expected one of {sorted(ALL_SCORE_SUFFIXES)}"
        )
    data = await file.read()
    if len(data) > MAX_SCORE_BYTES:
        raise UnprocessableError("score file exceeds 10 MB")
    upload_id = uuid4().hex
    dest_dir = settings.uploads_dir / "scores"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{upload_id}{suffix}"
    dest.write_bytes(data)

    meta_extra: dict[str, object] = {}
    if suffix in MUSESCORE_SUFFIXES:
        # Convert once, here, and point the upload at the MusicXML: every later read
        # (parse_score, score_to_chord_events per part) then sees a music21-native file.
        if not _looks_plausible(suffix, data[:16]):
            dest.unlink(missing_ok=True)
            raise UnprocessableError(f"{filename!r} does not look like a {suffix} file")
        try:
            dest = await to_musicxml(
                dest,
                dest_dir / f"{upload_id}.musicxml",
                mscore_bin=settings.mscore_bin,
                timeout_s=settings.score_convert_timeout,
            )
        except MuseScoreError as exc:
            (dest_dir / f"{upload_id}{suffix}").unlink(missing_ok=True)
            raise UnprocessableError(str(exc)) from exc
        meta_extra = {"converted_from": suffix, "converter": "musescore"}

    try:
        info = await run_in_threadpool(parse_score, dest)
    except UnsupportedScore as exc:
        dest.unlink(missing_ok=True)
        raise UnprocessableError(str(exc)) from exc
    await UploadRepo(session).add(
        UploadRow(
            id=upload_id,
            kind="score",
            filename=filename,
            path=str(dest),
            size_bytes=len(data),
            meta={**info.model_dump(mode="json"), **meta_extra},
        )
    )
    log.info("upload.score", upload_id=upload_id, filename=filename, parts=len(info.parts))
    return ScoreUploadResponse(
        upload_id=upload_id,
        filename=filename,
        title=info.title,
        artist=info.artist,
        parts=info.parts,
    )


# ---------------------------------------------------------------------------------- audio


class AudioUploadResponse(BaseModel):
    upload_id: str
    filename: str
    duration_s: float | None = None
    sample_rate: int | None = None


def sniff_audio(head: bytes) -> str | None:
    """Return the container kind (``mp3``/``wav``/``m4a``/``flac``/``ogg``) from magic bytes."""
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"OggS"):
        return "ogg"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"  # ID3 tag or an MPEG frame sync word
    return None


@router.post("/audio", response_model=AudioUploadResponse, status_code=201)
async def upload_audio(
    file: UploadFile, session: SessionDep, settings: SettingsDep
) -> AudioUploadResponse:
    """Upload a recording (mp3/wav/m4a/flac/ogg, <= 50 MB) for the audio tier; pass the returned
    ``upload_id`` in ``POST /jobs``."""
    filename = Path(file.filename or "audio.wav").name
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise UnprocessableError(
            f"unsupported audio type {suffix!r}; expected one of {sorted(AUDIO_SUFFIXES)}"
        )
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise UnprocessableError("audio file exceeds 50 MB")
    kind = sniff_audio(data[:16])
    if kind is None:
        raise UnprocessableError(f"{filename!r} does not look like an audio file")
    upload_id = uuid4().hex
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / f"{upload_id}{suffix}"
    dest.write_bytes(data)
    meta: dict[str, object] = {"container": kind}
    duration_s: float | None = None
    sample_rate: int | None = None
    try:
        info = await probe_audio(dest, settings.ffmpeg_bin)
    except FfmpegError as exc:
        log.warning("upload.audio.probe_failed", upload_id=upload_id, error=str(exc))
        meta["probe_error"] = str(exc)
    else:
        duration_s, sample_rate = info.duration_s, info.sample_rate
        meta.update(info.as_dict())
    await UploadRepo(session).add(
        UploadRow(
            id=upload_id,
            kind="audio",
            filename=filename,
            path=str(dest),
            size_bytes=len(data),
            meta=meta,
        )
    )
    log.info("upload.audio", upload_id=upload_id, filename=filename, duration_s=duration_s)
    return AudioUploadResponse(
        upload_id=upload_id, filename=filename, duration_s=duration_s, sample_rate=sample_rate
    )
