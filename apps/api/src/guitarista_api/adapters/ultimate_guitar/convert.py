"""Turn Ultimate Guitar page content into the canonical ``Tab``.

Two content flavours:

* **Tabs** pages carry ASCII tablature inside ``[tab]...[/tab]`` blocks::

      e|-3-----3--3--|
      B|-3-----3--3--|
      ...

  ``parse_ascii_tab`` walks the six string lines column by column: a column where any string has
  a fret digit is a beat (chord), ``|`` columns are bar lines, ``x`` is a dead note and
  ``h p / \\ b ~`` become note techniques. Two adjacent digits on one line are one fret (``10``,
  ``12``) when the other strings are silent in the second column. ASCII tab has no rhythm, so
  beats are uniform eighths (warned) and bars come from ``|`` when they are sane, otherwise beats
  are packed eight per measure.

* **Chords** pages carry ``[ch]F#m7[/ch]`` markup with ``[Section]`` headers and lyric lines in
  ``[tab]`` blocks. Each chord line becomes one measure with one beat per chord; notes come from
  ``services.chord_voicings`` (unknown symbols keep the name, empty notes, and a warning).

Both honour the page's capo and tuning (``"E A D G B E"`` low → high is turned into our
high → low MIDI list). Confidence is 0.6: real content, guessed rhythm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from guitarista_api.adapters.ultimate_guitar.parse import UGTabPage
from guitarista_api.domain.enums import TabSourceKind
from guitarista_api.domain.song import Song
from guitarista_api.domain.tab import (
    Beat,
    Duration,
    Measure,
    Note,
    Tab,
    TimeSignature,
    Track,
    Voice,
)
from guitarista_api.services.chord_voicings import voicing_for
from guitarista_api.solver.instrument import NOTE_NAMES, TUNINGS

log = structlog.get_logger(__name__)

STANDARD_TUNING = list(TUNINGS["standard"])
DEFAULT_TEMPO = 100.0
CONFIDENCE = 0.6
BEATS_PER_PACKED_MEASURE = 8
MAX_BEATS_PER_BAR = 16
MAX_TWO_DIGIT_FRET = 24
MIN_ASCII_NOTES = 8
"""Below this many notes an ASCII parse is considered a failure (intro-only scraps, lyrics)."""

_TAB_BLOCK_RE = re.compile(r"\[tab\](.*?)\[/tab\]", re.DOTALL | re.IGNORECASE)
_CH_RE = re.compile(r"\[ch\](.*?)\[/ch\]", re.IGNORECASE | re.DOTALL)
_SECTION_RE = re.compile(r"^\s*\[(?!/?(?:ch|tab)\])([^\[\]]{1,40})\]\s*$", re.IGNORECASE)
_TAG_RE = re.compile(r"\[/?(?:tab|ch)\]", re.IGNORECASE)
_STRING_LINE_RE = re.compile(
    r"^\s*(?P<label>[A-Ga-g][#b♯♭]?)?\s*(?P<sep>[|:]{1,2})?(?P<body>[-\d|hpbrHPBR/\\~xX^*()\s]*)$"
)
_TRAILING_ANNOTATION_RE = re.compile(r"\|\s+\S.*$|\|\s*[xX]\d+.*$")
_TECH_CHARS = {
    "h": "hammer",
    "p": "pull",
    "/": "slide",
    "\\": "slide",
    "b": "bend",
    "r": "release",
    "~": "vibrato",
    "^": "bend",
}
_NOTE_PC = {name: i for i, name in enumerate(NOTE_NAMES)}
_FLATS = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}


class UGConvertError(Exception):
    """The page content could not be turned into a usable tab."""


# --------------------------------------------------------------------------- tuning / capo


def parse_tuning_names(value: str | None) -> list[int] | None:
    """``"E A D G B E"`` (low → high, as UG writes it) -> ``[64, 59, 55, 50, 45, 40]``.

    Octaves are inferred: the lowest string lands in B1..A#2 and every next string is the nearest
    pitch above the previous one. Returns ``None`` for anything unparsable.
    """
    if not value:
        return None
    names = [n for n in re.split(r"[\s,]+", value.strip()) if n]
    if len(names) < 4 or len(names) > 8:
        return None
    pcs: list[int] = []
    for raw in names:
        name = raw.strip().upper().replace("♯", "#").replace("♭", "B")
        name = _FLATS.get(name, name)
        if name not in _NOTE_PC:
            return None
        pcs.append(_NOTE_PC[name])
    low_to_high = [35 + ((pcs[0] - 11) % 12)]
    for pc in pcs[1:]:
        prev = low_to_high[-1]
        low_to_high.append(prev + ((pc - prev) % 12 or 12))
    return list(reversed(low_to_high))


def resolve_tuning(page: UGTabPage, warnings: list[str]) -> list[int]:
    tuning = parse_tuning_names(page.tuning_value)
    if tuning is None:
        if page.tuning_value:
            warnings.append(f"unrecognized tuning {page.tuning_value!r}; assuming standard")
        return list(STANDARD_TUNING)
    return tuning


# --------------------------------------------------------------------------- ASCII tab


@dataclass(slots=True)
class AsciiNote:
    string: int
    fret: int
    dead: bool = False
    tech: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AsciiBeat:
    notes: list[AsciiNote] = field(default_factory=list)


@dataclass(slots=True)
class AsciiParse:
    measures: list[list[AsciiBeat]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    systems: int = 0

    @property
    def note_count(self) -> int:
        return sum(len(b.notes) for m in self.measures for b in m)

    @property
    def beats(self) -> list[AsciiBeat]:
        return [b for m in self.measures for b in m]


def _string_line(line: str) -> tuple[str, str] | None:
    """Return ``(label, body)`` when ``line`` looks like one string of ASCII tab."""
    line = line.rstrip()
    if not line or "[" in line or "]" in line:
        return None
    match = _STRING_LINE_RE.match(line)
    if not match:
        cut = _TRAILING_ANNOTATION_RE.sub("|", line)
        match = _STRING_LINE_RE.match(cut) if cut != line else None
        if not match:
            return None
    body = match.group("body")
    if body.count("-") < 2 or not re.search(r"[\d|x]", body):
        return None
    return (match.group("label") or "").strip(), body


def _string_groups(text: str, n_strings: int, warnings: list[str]) -> list[list[tuple[str, str]]]:
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for raw in text.split("\n"):
        parsed = _string_line(raw)
        if parsed is None:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(parsed)
    if current:
        groups.append(current)
    systems: list[list[tuple[str, str]]] = []
    for group in groups:
        if len(group) == n_strings:
            systems.append(group)
        elif len(group) >= 4:
            warnings.append(
                f"skipped a tab block with {len(group)} string lines (expected {n_strings})"
            )
    return systems


def _orientation_reversed(labels: list[str], tuning: list[int]) -> bool:
    """True when labels read low → high (string 6 on top), so lines must be flipped."""
    if not all(labels) or len(labels) != len(tuning):
        return False
    letters = [lab[0].upper() for lab in labels]
    expected = [NOTE_NAMES[p % 12][0] for p in tuning]  # high → low
    return letters != expected and letters == list(reversed(expected))


def _parse_system(
    lines: list[tuple[str, str]], tuning: list[int], warnings: list[str]
) -> tuple[list[AsciiBeat], list[int]]:
    """Return beats of one system and the beat indices that start a new bar."""
    labels = [lab for lab, _ in lines]
    bodies = [body for _, body in lines]
    if _orientation_reversed(labels, tuning):
        bodies.reverse()
    width = max(len(b) for b in bodies)
    bodies = [b.ljust(width, "-") for b in bodies]
    n = len(bodies)
    consumed = [[False] * width for _ in range(n)]
    beats: list[AsciiBeat] = []
    bar_starts: list[int] = []
    for col in range(width):
        bars = sum(1 for b in bodies if b[col] == "|")
        if bars and bars * 2 >= n:
            if not bar_starts or bar_starts[-1] != len(beats):
                bar_starts.append(len(beats))
            continue
        beat = AsciiBeat()
        for i, body in enumerate(bodies):
            ch = body[col]
            if consumed[i][col]:
                continue
            string = i + 1
            if ch in "xX":
                beat.notes.append(AsciiNote(string=string, fret=0, dead=True))
                continue
            if not ch.isdigit():
                continue
            fret = int(ch)
            nxt = body[col + 1] if col + 1 < width else ""
            if nxt.isdigit():
                two = int(ch + nxt)
                others_silent = all(not bodies[j][col + 1].isdigit() for j in range(n) if j != i)
                if two <= MAX_TWO_DIGIT_FRET and others_silent:
                    fret = two
                    consumed[i][col + 1] = True
            tech = _techniques(body, col, col + (2 if fret >= 10 else 1))
            beat.notes.append(AsciiNote(string=string, fret=fret, tech=tech))
        if beat.notes:
            beats.append(beat)
    return beats, bar_starts


def _techniques(body: str, start: int, end: int) -> list[str]:
    tech: list[str] = []
    before = body[start - 1] if start > 0 else ""
    after = body[end] if end < len(body) else ""
    for ch in (before, after):
        name = _TECH_CHARS.get(ch.lower()) if ch else None
        if name and name not in tech:
            tech.append(name)
    return tech


def parse_ascii_tab(content: str, tuning: list[int] | None = None) -> AsciiParse:
    """Parse every ASCII tab system in ``content`` (inside ``[tab]`` blocks or bare)."""
    tuning = tuning or STANDARD_TUNING
    result = AsciiParse()
    text = content.replace("\r\n", "\n")
    blocks = _TAB_BLOCK_RE.findall(text) or [_TAG_RE.sub("", text)]
    all_beats: list[AsciiBeat] = []
    segments: list[list[AsciiBeat]] = []
    for block in blocks:
        for system in _string_groups(block, len(tuning), result.warnings):
            beats, bar_starts = _parse_system(system, tuning, result.warnings)
            if not beats:
                continue
            result.systems += 1
            all_beats.extend(beats)
            cuts = sorted({0, *bar_starts, len(beats)})
            for a, b in zip(cuts, cuts[1:], strict=False):
                if b > a:
                    segments.append(beats[a:b])
    if not all_beats:
        return result
    result.warnings.append(
        "ASCII tab has no rhythm information; notes are rendered as uniform eighth notes"
    )
    if segments and all(len(seg) <= MAX_BEATS_PER_BAR for seg in segments):
        result.measures = segments
    else:
        result.warnings.append(
            f"bar lines were unusable; beats packed {BEATS_PER_PACKED_MEASURE} per measure"
        )
        result.measures = [
            all_beats[i : i + BEATS_PER_PACKED_MEASURE]
            for i in range(0, len(all_beats), BEATS_PER_PACKED_MEASURE)
        ]
    return result


def ascii_to_tab(page: UGTabPage, song: Song | None = None) -> Tab:
    warnings: list[str] = []
    tuning = resolve_tuning(page, warnings)
    capo = page.capo or 0
    parsed = parse_ascii_tab(page.content, tuning)
    if parsed.note_count < MIN_ASCII_NOTES:
        raise UGConvertError(
            f"ASCII tab parse found only {parsed.note_count} notes in {parsed.systems} systems"
        )
    warnings.extend(parsed.warnings)
    measures: list[Measure] = []
    for idx, beats in enumerate(parsed.measures, start=1):
        voice = Voice()
        for ab in beats:
            notes = [
                Note(
                    string=an.string,
                    fret=an.fret,
                    dead=an.dead,
                    pitch_midi=None if an.dead else tuning[an.string - 1] + capo + an.fret,
                    tech=an.tech,
                )
                for an in ab.notes
                if an.fret <= 30
            ]
            voice.beats.append(Beat(duration=Duration(num=1, den=8), notes=notes))
        measures.append(Measure(number=idx, voices=[voice]))
    return _tab(page, song, tuning, capo, measures, warnings)


# --------------------------------------------------------------------------- chords


def _chord_lines(content: str, warnings: list[str]) -> list[tuple[str | None, list[str]]]:
    """``[(section_marker_or_None, [chord names])]`` per chord line; ASCII tab blocks dropped."""

    def _drop_ascii(match: re.Match[str]) -> str:
        block = match.group(1)
        if len(_string_groups(block, 6, [])) or len(_string_groups(block, 4, [])):
            return "\n"
        return block

    text = _TAB_BLOCK_RE.sub(_drop_ascii, content.replace("\r\n", "\n"))
    lines: list[tuple[str | None, list[str]]] = []
    pending: str | None = None
    for raw in text.split("\n"):
        header = _SECTION_RE.match(raw)
        if header:
            pending = header.group(1).strip()
            continue
        chords = [c.strip() for c in _CH_RE.findall(raw) if c.strip()]
        if not chords:
            continue
        lines.append((pending, chords))
        pending = None
    return lines


def _chord_duration(count: int) -> Duration:
    for den in (1, 2, 4, 8, 16):
        if count <= den:
            return Duration(num=1, den=den)
    return Duration(num=1, den=16)


def chords_to_tab(page: UGTabPage, song: Song | None = None) -> Tab:
    warnings: list[str] = []
    tuning = resolve_tuning(page, warnings)
    capo = page.capo or 0
    lines = _chord_lines(page.content, warnings)
    if not lines:
        raise UGConvertError("no [ch] chord symbols found on the page")
    voicings_ok = len(tuning) == 6
    if not voicings_ok:
        warnings.append("chord voicings are only available for 6-string tunings")
    elif tuning != STANDARD_TUNING:
        warnings.append("chord voicings assume standard tuning; pitches follow the page tuning")
    warnings.append("chord sheet: one measure per chord line, rhythm is a guess")
    unknown: list[str] = []
    measures: list[Measure] = []
    for idx, (marker, chords) in enumerate(lines, start=1):
        duration = _chord_duration(len(chords))
        voice = Voice()
        for name in chords:
            notes: list[Note] = []
            voicing = voicing_for(name) if voicings_ok else None
            if voicing is None:
                if name not in unknown:
                    unknown.append(name)
            else:
                notes = [
                    Note(string=s, fret=f, pitch_midi=tuning[s - 1] + capo + f) for s, f in voicing
                ]
            voice.beats.append(Beat(duration=duration, notes=notes, chord_name=name))
        measures.append(Measure(number=idx, voices=[voice], marker=marker))
    if unknown:
        warnings.append(f"no voicing for chord(s): {', '.join(unknown[:12])}")
    return _tab(page, song, tuning, capo, measures, warnings)


# --------------------------------------------------------------------------- shared


def page_to_tab(page: UGTabPage, song: Song | None = None) -> Tab:
    """Dispatch on the page type (``Chords`` -> chord sheet, anything else -> ASCII tab)."""
    return chords_to_tab(page, song) if page.is_chords else ascii_to_tab(page, song)


def _tab(
    page: UGTabPage,
    song: Song | None,
    tuning: list[int],
    capo: int,
    measures: list[Measure],
    warnings: list[str],
) -> Tab:
    track = Track(name="Guitar", tuning=tuning, capo=capo, measures=measures)
    tab = Tab(
        song_id=song.id if song else None,
        title=page.song_name or (song.title if song else "Untitled"),
        artist=page.artist_name or (song.artist if song else None) or None,
        source=TabSourceKind.ULTIMATE_GUITAR,
        source_ref=f"ug:{page.id}",
        confidence=CONFIDENCE,
        tempo_bpm=DEFAULT_TEMPO,
        time_signature=TimeSignature(),
        tracks=[track],
        warnings=warnings,
    )
    if measures and page.tonality:
        measures[0].marker = measures[0].marker or f"Key: {page.tonality}"
    return tab
