"""Serialize the canonical Tab model to alphaTex (alphaTab's text format).

Syntax reference: https://www.alphatab.net/docs/alphatex/ (document-structure, bar-metadata,
beat-properties, note-properties). Notable conventions:

* ``\\tuning`` lists note names highest string first (``e4 b3 g3 d3 a2 e2``).
* ``fret.string`` in alphaTex *text* numbers strings with **1 = highest** string, matching our
  canonical model, so string numbers are emitted unchanged. (alphaTab's internal ``Note.string``
  uses 1 = lowest; the importer performs that flip. Pinned against alphaTab 1.8.4: with
  ``\tuning e4 b3 g3 d3 a2 e2``, ``0.1.4`` sounds MIDI 64 and ``0.6.4`` sounds 40.)
* A beat's ``.duration`` suffix is remembered for following beats.
* Since alphaTex 1.7 the ``.`` separator between metadata and body is optional; we still emit
  it for compatibility with the syntax documented for 1.x (``METADATA_SEPARATOR``).
"""

from __future__ import annotations

from guitarista_api.domain.tab import Beat, Duration, Measure, Note, Tab, Track
from guitarista_api.solver.instrument import midi_to_name

METADATA_SEPARATOR = "."

# canonical finger 0..4 (thumb..pinky) -> alphaTab lf 1..5
_FINGER_TO_LF = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def tuning_names(tuning: list[int]) -> str:
    return " ".join(midi_to_name(p).lower() for p in tuning)


def tab_to_alphatex(tab: Tab, track_index: int = 0) -> str:
    if not tab.tracks:
        raise ValueError("tab has no tracks")
    track = tab.tracks[track_index]
    header = _header(tab, track)
    body = _body(tab, track)
    return "\n".join([*header, METADATA_SEPARATOR, body]) + "\n"


def _header(tab: Tab, track: Track) -> list[str]:
    lines = [f"\\title {_quote(tab.title)}"]
    if tab.artist:
        lines.append(f"\\artist {_quote(tab.artist)}")
    lines.append(f"\\tempo {_fmt_number(tab.tempo_bpm)}")
    lines.append(f"\\tuning ({tuning_names(track.tuning)})")
    if track.capo:
        lines.append(f"\\capo {track.capo}")
    lines.append(f"\\ts {tab.time_signature.numerator} {tab.time_signature.denominator}")
    return lines


def _body(tab: Tab, track: Track) -> str:
    num_voices = max((len(m.voices) for m in track.measures), default=1)
    if num_voices <= 1:
        return _voice_body(track, 0, tab)
    chunks = [f"\\voice\n{_voice_body(track, v, tab)}" for v in range(num_voices)]
    return "\n".join(chunks)


def _voice_body(track: Track, voice_index: int, tab: Tab) -> str:
    bars: list[str] = []
    state = _DurationState()
    for i, measure in enumerate(track.measures):
        bars.append(_measure(measure, voice_index, state, first=i == 0, tab=tab))
    return " |\n".join(bars)


class _DurationState:
    """Tracks the alphaTex 'remembered duration' so we only emit suffixes on change."""

    def __init__(self) -> None:
        self.den: int | None = None

    def suffix(self, duration: Duration) -> str:
        if duration.den == self.den:
            return ""
        self.den = duration.den
        return f".{duration.den}"


def _measure(
    measure: Measure, voice_index: int, state: _DurationState, *, first: bool, tab: Tab
) -> str:
    tags = _bar_tags(measure, first=first, tab=tab)
    beats = measure.voices[voice_index].beats if voice_index < len(measure.voices) else []
    content = " ".join(_beat(b, state) for b in beats) or "r"
    return f"{tags} {content}".strip()


def _bar_tags(measure: Measure, *, first: bool, tab: Tab) -> str:
    tags: list[str] = []
    ts = measure.time_signature
    if ts is not None and not first:
        tags.append(f"\\ts {ts.numerator} {ts.denominator}")
    if measure.repeat_start:
        tags.append("\\ro")
    if measure.repeat_end:
        tags.append(f"\\rc {measure.repeat_end}")
    if measure.marker:
        tags.append(f"\\section {_quote(measure.marker)}")
    return " ".join(tags)


def _beat(beat: Beat, state: _DurationState) -> str:
    suffix = state.suffix(beat.duration)
    if beat.is_rest:
        content = f"r{suffix}"
    elif len(beat.notes) == 1:
        content = f"{_note(beat.notes[0])}{suffix}"
    else:
        inner = " ".join(_note(note) for note in beat.notes)
        content = f"({inner}){suffix}"
    effects = _beat_effects(beat)
    return f"{content} {{{effects}}}" if effects else content


def _beat_effects(beat: Beat) -> str:
    parts: list[str] = []
    if beat.duration.dots == 1:
        parts.append("d")
    elif beat.duration.dots >= 2:
        parts.append("dd")
    if beat.duration.tuplet:
        actual, normal = beat.duration.tuplet
        parts.append(f"tu {actual}" if (actual, normal) == (3, 2) else f"tu {actual} {normal}")
    if beat.tempo_bpm:
        parts.append(f"tempo {_fmt_number(beat.tempo_bpm)}")
    if beat.chord_name:
        parts.append(f"ch {_quote(beat.chord_name)}")
    if beat.text:
        parts.append(f"txt {_quote(beat.text)}")
    return " ".join(parts)


def _note(note: Note) -> str:
    s = note.string
    if note.tie:
        head = f"-.{s}"
    elif note.dead:
        head = f"x.{s}"
    else:
        head = f"{note.fret}.{s}"
    effects: list[str] = []
    if note.ghost:
        effects.append("g")
    if note.finger is not None and note.finger in _FINGER_TO_LF:
        effects.append(f"lf {_FINGER_TO_LF[note.finger]}")
    effects.extend(_TECH_MAP[t] for t in note.tech if t in _TECH_MAP)
    return f"{head}{{{' '.join(effects)}}}" if effects else head


_TECH_MAP = {
    "hammer": "h",
    "pull": "h",
    "slide": "sl",
    "vibrato": "v",
    "palm_mute": "pm",
    "let_ring": "lr",
    "staccato": "st",
    "accent": "ac",
    "harmonic": "nh",
}
