"""JSON shapes shared between the sidecar CLI and its caller (apps/api).

Keep these in sync with ``NoteEvent`` / ``TranscriptionResult`` in
``apps/api/src/guitarista_api/domain``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict

Backend = Literal["coreml", "tf", "onnx", "tflite"]
Device = Literal["mps", "cpu"]
ModelName = Literal["basic-pitch", "tabcnn"]

BASIC_PITCH_MODEL = "basic-pitch/icassp2022"


@dataclass(slots=True)
class NoteEvent:
    onset_s: float
    offset_s: float
    pitch_midi: int
    velocity: float  # 0..1 (basic-pitch amplitude)
    pitch_bend: list[int] | None = None
    confidence: float | None = None  # 0..1; basic-pitch has no separate score, so = velocity
    string: int | None = None  # canonical: 1 = highest string; only models with a string head set it
    fret: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TranscriptionResult:
    notes: list[NoteEvent]
    tempo_bpm: float | None
    source_audio: str
    duration_s: float
    beats_s: list[float] = field(default_factory=list)  # tracked beat times, empty if not estimated
    stem: str = "mix"
    model: str = BASIC_PITCH_MODEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes": [n.to_dict() for n in self.notes],
            "tempo_bpm": self.tempo_bpm,
            "beats_s": self.beats_s,
            "source_audio": self.source_audio,
            "stem": self.stem,
            "model": self.model,
            "duration_s": self.duration_s,
        }


class VersionResult(TypedDict):
    version: str


class ProbeResult(TypedDict):
    basic_pitch: bool
    backend: Backend | None
    demucs: bool
    tabcnn: bool
    device: Device
    torch: str | None


class TranscribeSummary(TypedDict):
    ok: bool
    out: str
    note_count: int
    tempo_bpm: float | None


class SeparateResult(TypedDict):
    stems: dict[str, str]
    model: str


class ErrorResult(TypedDict):
    error: str
    type: str


class ProgressLine(TypedDict):
    progress: float
    stage: str


@dataclass(slots=True)
class TranscribeOptions:
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    min_note_ms: float = 58.0
    fmin: float | None = 80.0
    fmax: float | None = 1300.0
    estimate_tempo: bool = False
    model: ModelName = "basic-pitch"


@dataclass(slots=True)
class SeparateOptions:
    model: str = "htdemucs_6s"
    stems: list[str] = field(default_factory=lambda: ["guitar", "other"])
    device: Literal["auto", "mps", "cpu"] = "auto"
