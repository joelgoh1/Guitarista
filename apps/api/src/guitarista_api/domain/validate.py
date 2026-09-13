from __future__ import annotations

from guitarista_api.domain.tab import Beat, Tab, Track

MAX_FRET = 30


def validate_tab(tab: Tab) -> list[str]:
    """Return a list of human-readable consistency errors (empty when the tab is valid)."""
    errors: list[str] = []
    for t_idx, track in enumerate(tab.tracks):
        for measure in track.measures:
            for v_idx, voice in enumerate(measure.voices):
                for b_idx, beat in enumerate(voice.beats):
                    where = f"track {t_idx} m{measure.number} v{v_idx} b{b_idx}"
                    errors.extend(_validate_beat(beat, track, where))
    return errors


def _validate_beat(beat: Beat, track: Track, where: str) -> list[str]:
    errors: list[str] = []
    seen: set[int] = set()
    n_strings = len(track.tuning)
    for note in beat.notes:
        if not 1 <= note.string <= n_strings:
            errors.append(f"{where}: string {note.string} out of range 1..{n_strings}")
            continue
        if not 0 <= note.fret <= MAX_FRET:
            errors.append(f"{where}: fret {note.fret} out of range 0..{MAX_FRET}")
        if note.string in seen:
            errors.append(f"{where}: duplicate string {note.string} within beat")
        seen.add(note.string)
        if note.pitch_midi is not None and not note.dead:
            expected = track.tuning[note.string - 1] + track.capo + note.fret
            if expected != note.pitch_midi:
                errors.append(
                    f"{where}: string {note.string} fret {note.fret} sounds {expected}, "
                    f"pitch_midi says {note.pitch_midi}"
                )
    return errors
