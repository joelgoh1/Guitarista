"""Built-in open/barre guitar voicings for common chord symbols (standard tuning, 6 strings).

Voicings are written low → high like a chord chart (``x32010`` = C). Explicit open shapes are
listed first; anything else is derived by sliding the E-shape or A-shape barre family up the neck,
which is how players finger e.g. ``F#m7`` (E-shape m7 barred at 2 = ``242222``).

``voicing_for("F#m7") -> [(6, 2), (5, 4), (4, 2), (3, 2), (2, 2), (1, 2)]`` as ``(string, fret)``
with string 1 = highest. Returns ``None`` for symbols it cannot voice (callers keep the chord name
and emit a warning).
"""

from __future__ import annotations

import re
from functools import lru_cache

_ROOT_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_CHORD_RE = re.compile(
    r"^\s*(?P<root>[A-G])(?P<acc>[#♯b♭]?)(?P<qual>[^/\s]*)(?:/(?P<bass>[A-G][#♯b♭]?))?\s*$"
)

Voicing = tuple[int | None, ...]
"""Six frets low → high; ``None`` = muted string."""


def _v(chart: str) -> Voicing:
    out: list[int | None] = []
    for ch in chart.split() if " " in chart else chart:
        out.append(None if ch.lower() == "x" else int(ch))
    if len(out) != 6:
        raise ValueError(f"voicing {chart!r} must have 6 strings")
    return tuple(out)


# (root pitch class, quality) -> explicit open voicing
OPEN_VOICINGS: dict[tuple[int, str], Voicing] = {
    (0, ""): _v("x32010"),
    (0, "maj7"): _v("x32000"),
    (0, "7"): _v("x32310"),
    (0, "add9"): _v("x32030"),
    (0, "sus4"): _v("x33011"),
    (0, "sus2"): _v("x30013"),
    (2, ""): _v("xx0232"),
    (2, "m"): _v("xx0231"),
    (2, "7"): _v("xx0212"),
    (2, "m7"): _v("xx0211"),
    (2, "sus2"): _v("xx0230"),
    (2, "sus4"): _v("xx0233"),
    (2, "maj7"): _v("xx0222"),
    (2, "5"): _v("xx023x"),
    (4, ""): _v("022100"),
    (4, "m"): _v("022000"),
    (4, "7"): _v("020100"),
    (4, "m7"): _v("020000"),
    (4, "sus4"): _v("022200"),
    (4, "7sus4"): _v("020200"),
    (4, "maj7"): _v("021100"),
    (4, "add9"): _v("022102"),
    (4, "5"): _v("022xxx"),
    (5, ""): _v("133211"),
    (5, "maj7"): _v("xx3210"),
    (7, ""): _v("320003"),
    (7, "7"): _v("320001"),
    (7, "maj7"): _v("320002"),
    (7, "sus4"): _v("330013"),
    (7, "add9"): _v("320203"),
    (7, "5"): _v("355xxx"),
    (9, ""): _v("x02220"),
    (9, "m"): _v("x02210"),
    (9, "7"): _v("x02020"),
    (9, "m7"): _v("x02010"),
    (9, "sus2"): _v("x02200"),
    (9, "sus4"): _v("x02230"),
    (9, "7sus4"): _v("x02030"),
    (9, "maj7"): _v("x02120"),
    (9, "add9"): _v("x02420"),
    (9, "5"): _v("x022xx"),
    (11, ""): _v("x24442"),
    (11, "m"): _v("x24432"),
    (11, "7"): _v("x21202"),
    (11, "m7"): _v("x20202"),
    (11, "7sus4"): _v("x22202"),
}

# Barre families: shapes rooted on E (pc 4, root on string 6) and A (pc 9, root on string 5).
E_SHAPES: dict[str, Voicing] = {
    "": _v("022100"),
    "m": _v("022000"),
    "7": _v("020100"),
    "m7": _v("020000"),
    "sus4": _v("022200"),
    "7sus4": _v("020200"),
    "maj7": _v("021100"),
    "add9": _v("022102"),
    "5": _v("022xxx"),
    "m7b5": _v("0x0000"),
}
A_SHAPES: dict[str, Voicing] = {
    "": _v("x02220"),
    "m": _v("x02210"),
    "7": _v("x02020"),
    "m7": _v("x02010"),
    "sus2": _v("x02200"),
    "sus4": _v("x02230"),
    "7sus4": _v("x02030"),
    "maj7": _v("x02120"),
    "add9": _v("x02420"),
    "5": _v("x022xx"),
    "dim": _v("x0121x"),
    "m6": _v("x02212"),
    "6": _v("x02222"),
}

_QUALITY_ALIASES: dict[str, str] = {
    "maj": "",
    "M": "",
    "major": "",
    "min": "m",
    "minor": "m",
    "-": "m",
    "sus": "sus4",
    "M7": "maj7",
    "Maj7": "maj7",
    "ma7": "maj7",
    "min7": "m7",
    "-7": "m7",
    "2": "add9",
    "add2": "add9",
    "dom7": "7",
    "7sus": "7sus4",
    "°": "dim",
    "o": "dim",
}


def parse_chord_symbol(name: str) -> tuple[int, str] | None:
    """``"F#m7/A" -> (6, "m7")``; ``None`` when the text is not a chord symbol."""
    match = _CHORD_RE.match(name)
    if not match:
        return None
    pc = _ROOT_PC[match.group("root")]
    acc = match.group("acc")
    if acc in ("#", "♯"):
        pc += 1
    elif acc in ("b", "♭"):
        pc -= 1
    qual = match.group("qual").strip("()")
    qual = _QUALITY_ALIASES.get(qual, qual)
    return pc % 12, qual


def _shift(shape: Voicing, by: int) -> Voicing:
    return tuple(None if f is None else f + by for f in shape)


@lru_cache(maxsize=512)
def voicing_for(name: str) -> tuple[tuple[int, int], ...] | None:
    """Fretted ``(string, fret)`` notes for a chord symbol (string 1 = highest), or ``None``."""
    parsed = parse_chord_symbol(name)
    if parsed is None:
        return None
    pc, qual = parsed
    voicing = OPEN_VOICINGS.get((pc, qual))
    if voicing is None:
        options: list[Voicing] = []
        if qual in E_SHAPES:
            options.append(_shift(E_SHAPES[qual], (pc - 4) % 12))
        if qual in A_SHAPES:
            options.append(_shift(A_SHAPES[qual], (pc - 9) % 12))
        if not options:
            return None
        # lowest barre position wins (ties -> E-shape, which carries the root on string 6)
        voicing = min(options, key=lambda v: max(f for f in v if f is not None))
    return tuple((6 - idx, fret) for idx, fret in enumerate(voicing) if fret is not None)
