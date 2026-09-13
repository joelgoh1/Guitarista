/**
 * Note-name parsing and MIDI conversion.
 *
 * Conventions:
 * - Scientific pitch notation with MIDI 60 = C4 (so E2 = 40, E4 = 64).
 * - Accidentals accepted on input: `♯`, `#`, `♭`, `b`, and `-` (music21 flat).
 *   Because `-` means flat, negative octaves are not parseable: `C-1` is C♭1 (MIDI 23).
 *   `midiToNote(0..11)` still returns `C-1`-style names, which therefore do not round-trip.
 * - Output helpers default to unicode accidentals (`♯` / `♭`), which is what the
 *   chord JSON data uses.
 */

export type Letter = 'C' | 'D' | 'E' | 'F' | 'G' | 'A' | 'B';
export type Accidental = -1 | 0 | 1;

export interface ParsedNote {
  letter: Letter;
  accidental: Accidental;
  octave: number;
  midi: number;
}

const LETTER_TO_PC: Record<Letter, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const SHARP_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'] as const;
const FLAT_NAMES = ['C', 'D♭', 'D', 'E♭', 'E', 'F', 'G♭', 'G', 'A♭', 'A', 'B♭', 'B'] as const;

const NOTE_RE = /^\s*([A-Ga-g])\s*(♯|#|♭|b|-)?\s*(-?\d+)\s*$/u;

export function parseNote(name: string): ParsedNote {
  const m = NOTE_RE.exec(name);
  if (!m) throw new Error(`Invalid note name: "${name}"`);
  const letter = m[1]!.toUpperCase() as Letter;
  const acc = m[2];
  const accidental: Accidental = acc === undefined ? 0 : acc === '♯' || acc === '#' ? 1 : -1;
  const octave = Number.parseInt(m[3]!, 10);
  const midi = (octave + 1) * 12 + LETTER_TO_PC[letter] + accidental;
  if (midi < 0 || midi > 127) throw new Error(`Note out of MIDI range: "${name}" (${midi})`);
  return { letter, accidental, octave, midi };
}

export function noteToMidi(name: string): number {
  return parseNote(name).midi;
}

export interface MidiToNoteOptions {
  prefer?: 'sharp' | 'flat';
}

/** MIDI number → note name with unicode accidental, e.g. 61 → `C♯4` (or `D♭4`). */
export function midiToNote(midi: number, opts: MidiToNoteOptions = {}): string {
  if (!Number.isInteger(midi) || midi < 0 || midi > 127) {
    throw new Error(`MIDI value out of range: ${midi}`);
  }
  const names = opts.prefer === 'flat' ? FLAT_NAMES : SHARP_NAMES;
  const pc = midi % 12;
  const octave = Math.floor(midi / 12) - 1;
  return `${names[pc]}${octave}`;
}

/** 0..11 pitch class of a note name (C = 0). */
export function pitchClass(name: string): number {
  return ((noteToMidi(name) % 12) + 12) % 12;
}

/** Pitch class of a MIDI number. */
export function midiPitchClass(midi: number): number {
  return ((midi % 12) + 12) % 12;
}

/** Transpose by semitones; spelling follows `prefer` (default sharps). */
export function transpose(name: string, semitones: number, opts: MidiToNoteOptions = {}): string {
  return midiToNote(noteToMidi(name) + semitones, opts);
}

/** `C#4` / `Db3` / `E-2` → `C♯4` / `D♭3` / `E♭2`. */
export function toUnicodeAccidentals(name: string): string {
  return name.replace(/#/gu, '♯').replace(/([A-Ga-g])(?:b|-)(?=-?\d)/gu, '$1♭');
}

/** `C♯4` / `D♭3` → `C#4` / `Db3`. */
export function toAsciiAccidentals(name: string): string {
  return name.replace(/♯/gu, '#').replace(/♭/gu, 'b');
}

/** `C♯4` / `D♭3` → `C#4` / `D-3` (music21 spelling). */
export function toMusic21Name(name: string): string {
  return toAsciiAccidentals(name).replace(/([A-Ga-g])b(?=-?\d)/gu, '$1-');
}

/**
 * Canonical form: uppercase letter, unicode accidental, no whitespace.
 * `db3` → `D♭3`, `c#4` → `C♯4`, `E-2` → `E♭2`.
 */
export function normalizeNoteName(name: string): string {
  const p = parseNote(name);
  const acc = p.accidental === 1 ? '♯' : p.accidental === -1 ? '♭' : '';
  return `${p.letter}${acc}${p.octave}`;
}

/** True when two spellings refer to the same pitch (`C♯4` ~ `D♭4`). */
export function isEnharmonic(a: string, b: string): boolean {
  return noteToMidi(a) === noteToMidi(b);
}

export const PITCH_CLASS_NAMES_SHARP: readonly string[] = SHARP_NAMES;
export const PITCH_CLASS_NAMES_FLAT: readonly string[] = FLAT_NAMES;
