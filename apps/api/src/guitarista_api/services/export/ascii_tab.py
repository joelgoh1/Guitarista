"""Plain-text ASCII tablature, one line per string (highest string on top)."""

from __future__ import annotations

from guitarista_api.domain.tab import Beat, Tab
from guitarista_api.solver.instrument import midi_to_name

_MEASURES_PER_LINE = 4


def tab_to_ascii(tab: Tab, track_index: int = 0) -> str:
    if not tab.tracks:
        raise ValueError("tab has no tracks")
    track = tab.tracks[track_index]
    labels = [midi_to_name(p).rstrip("0123456789").ljust(2) for p in track.tuning]
    header = [tab.title + (f" - {tab.artist}" if tab.artist else "")]
    header.append(
        f"Tempo: {tab.tempo_bpm:g}  Time: "
        f"{tab.time_signature.numerator}/{tab.time_signature.denominator}"
    )
    if track.capo:
        header.append(f"Capo: {track.capo}")
    blocks: list[str] = []
    measures = track.measures
    for start in range(0, len(measures), _MEASURES_PER_LINE):
        chunk = measures[start : start + _MEASURES_PER_LINE]
        lines = [f"{labels[i]}|" for i in range(len(track.tuning))]
        for measure in chunk:
            cells = [_beat_cells(b, len(track.tuning)) for b in measure.voices[0].beats]
            for i in range(len(lines)):
                lines[i] += "-" + "".join(c[i] for c in cells) + "|"
        blocks.append("\n".join(lines))
    return "\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n"


def _beat_cells(beat: Beat, n: int) -> list[str]:
    width = 2 if all(note.fret < 10 for note in beat.notes) else 3
    cells = ["-" * (width + 1)] * n
    for note in beat.notes:
        text = "x" if note.dead else str(note.fret)
        if note.tie:
            text = "~"
        cells[note.string - 1] = text.ljust(width, "-") + "-"
    return cells
