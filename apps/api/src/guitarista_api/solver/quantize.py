"""Turn transcribed note events into a grid-aligned list of chord events.

Readability rules (why the defaults look the way they do):

* A beat map (``Grid.beats_s``) is preferred over a bare tempo: audio rarely starts on a beat, and a
  constant grid from ``t=0`` rounds every onset inconsistently, which shows up as spurious rests.
* Transcribers cut notes short (the frame activation drops as the string decays), so a gap up to
  ``fill_gap_steps`` before the next onset is treated as legato and the note is extended. Guitar tab
  readers expect rests only at real pauses.
* Strums spread onsets over 40–100 ms; grouping chains onsets so a strummed chord is one event.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from guitarista_api.domain.transcription import NoteEvent
from guitarista_api.solver.model import ChordEvent

MIN_BEAT_GAP_S = 0.1
"""Beats closer than this are duplicates from the tracker and are dropped."""


@dataclass(frozen=True, slots=True)
class Grid:
    tempo_bpm: float
    subdivision: int = 4
    """Grid steps per quarter note (4 = sixteenths)."""
    beats_s: tuple[float, ...] = ()
    """Optional beat times; with two or more, snapping follows this map (tempo drift and phase)."""

    @property
    def beat_s(self) -> float:
        return 60.0 / self.tempo_bpm

    @property
    def step_s(self) -> float:
        return self.beat_s / self.subdivision

    @property
    def step_fraction(self) -> Fraction:
        return Fraction(1, 4 * self.subdivision)

    def position(self, t: float) -> float:
        """Time in seconds → position in quarter notes from the grid origin (may be negative)."""
        b = self.beats_s
        if len(b) < 2:
            return t / self.beat_s
        i = min(max(bisect_right(b, t) - 1, 0), len(b) - 2)
        return i + (t - b[i]) / (b[i + 1] - b[i])

    def snap(self, t: float) -> int:
        return round(self.position(t) * self.subdivision)


def estimate_grid(
    notes: Sequence[NoteEvent],
    tempo_bpm: float | None,
    subdivision: int = 4,
    beats_s: Sequence[float] = (),
) -> Grid:
    """Build a grid from beat times, else a known tempo, else the median inter-onset interval."""
    beats = _clean_beats(beats_s)
    if len(beats) >= 2:
        if not (tempo_bpm and tempo_bpm > 0):
            gaps = sorted(b - a for a, b in zip(beats, beats[1:], strict=False))
            tempo_bpm = round(60.0 / gaps[len(gaps) // 2], 1)
        return Grid(tempo_bpm, subdivision, beats)
    if tempo_bpm and tempo_bpm > 0:
        return Grid(tempo_bpm, subdivision)
    onsets = sorted({n.onset_s for n in notes})
    gaps = [b - a for a, b in zip(onsets, onsets[1:], strict=False) if b - a > 0.05]
    if not gaps:
        return Grid(120.0, subdivision)
    gaps.sort()
    median = gaps[len(gaps) // 2]
    bpm = 60.0 / median
    while bpm > 200:
        bpm /= 2
    while bpm < 50:
        bpm *= 2
    return Grid(round(bpm, 1), subdivision)


def _clean_beats(beats_s: Sequence[float]) -> tuple[float, ...]:
    out: list[float] = []
    for b in sorted(float(x) for x in beats_s):
        if b < 0:
            continue
        if not out or b - out[-1] >= MIN_BEAT_GAP_S:
            out.append(b)
    return tuple(out)


def quantize(
    notes: Sequence[NoteEvent],
    grid: Grid,
    min_gap_s: float = 0.05,
    max_group_span_s: float = 0.12,
    max_polyphony: int = 6,
    fill_gap_steps: int = 2,
) -> list[ChordEvent]:
    """Snap note events to ``grid``, group near-simultaneous onsets, fill gaps with rests.

    ``min_gap_s`` chains onsets into one chord (a strum), up to ``max_group_span_s`` in total.
    Gaps of at most ``fill_gap_steps`` grid steps before the next onset are legato-filled instead
    of becoming rests.
    """
    if not notes:
        return []
    groups = _group_onsets(
        sorted(notes, key=lambda n: (n.onset_s, n.pitch_midi)), min_gap_s, max_group_span_s
    )
    raw_starts = [grid.snap(g[0].onset_s) for g in groups]
    shift = min(0, min(raw_starts))  # a beat map may place early notes before its origin
    starts = [s - shift for s in raw_starts]
    events: list[ChordEvent] = []
    cursor = 0
    for i, group in enumerate(groups):
        start = max(starts[i], cursor)
        next_start = starts[i + 1] if i + 1 < len(groups) else None
        end = _group_end(group, grid, shift, start, next_start, fill_gap_steps)
        if start > cursor:
            events.append(ChordEvent((), (start - cursor) * grid.step_fraction, len(events)))
        kept = _cap_polyphony(group, max_polyphony)
        pitches = tuple(n.pitch_midi for n in kept)
        hints = {n.pitch_midi: n.hint for n in kept if n.hint is not None}
        meta: dict[str, object] = {"source_notes": kept}
        if hints:
            meta["hints"] = hints
        events.append(ChordEvent(pitches, (end - start) * grid.step_fraction, len(events), meta))
        cursor = end
    return events


def _group_onsets(
    notes: list[NoteEvent], min_gap_s: float, max_span_s: float
) -> list[list[NoteEvent]]:
    groups: list[list[NoteEvent]] = []
    for n in notes:
        if (
            groups
            and n.onset_s - groups[-1][-1].onset_s <= min_gap_s
            and n.onset_s - groups[-1][0].onset_s <= max_span_s
        ):
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def _group_end(
    group: list[NoteEvent],
    grid: Grid,
    shift: int,
    start: int,
    next_start: int | None,
    fill_gap_steps: int,
) -> int:
    end = max(grid.snap(n.offset_s) for n in group) - shift
    end = max(end, start + 1)
    if next_start is None:
        # last event: let it ring to the end of its beat rather than end on a stray sixteenth
        beat_end = -(-end // grid.subdivision) * grid.subdivision
        return beat_end if beat_end - end <= fill_gap_steps else end
    limit = max(next_start, start + 1)
    if end > limit or limit - end <= fill_gap_steps:
        end = limit
    return end


def _cap_polyphony(group: list[NoteEvent], max_polyphony: int) -> list[NoteEvent]:
    """Most confident note per pitch, at most ``max_polyphony`` of them, sorted by pitch."""
    ranked = sorted(group, key=lambda n: (-n.confidence, -n.velocity, n.pitch_midi))
    uniq: dict[int, NoteEvent] = {}
    for n in ranked:
        uniq.setdefault(n.pitch_midi, n)
    kept = list(uniq.values())[:max_polyphony]
    return sorted(kept, key=lambda n: n.pitch_midi)
