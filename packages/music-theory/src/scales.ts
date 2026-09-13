import { midiPitchClass, midiToNote, noteToMidi } from './notes';

/** Interval patterns in semitones above the root (root included as 0). */
export const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],
  natural_minor: [0, 2, 3, 5, 7, 8, 10],
  harmonic_minor: [0, 2, 3, 5, 7, 8, 11],
  pentatonic_major: [0, 2, 4, 7, 9],
  pentatonic_minor: [0, 3, 5, 7, 10],
  blues: [0, 3, 5, 6, 7, 10],
  // Modes
  ionian: [0, 2, 4, 5, 7, 9, 11],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  phrygian: [0, 1, 3, 5, 7, 8, 10],
  lydian: [0, 2, 4, 6, 7, 9, 11],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  aeolian: [0, 2, 3, 5, 7, 8, 10],
  locrian: [0, 1, 3, 5, 6, 8, 10],
} as const satisfies Record<string, readonly number[]>;

export type ScaleId = keyof typeof SCALES;

export const SCALE_LABELS: Record<ScaleId, string> = {
  major: 'Major',
  natural_minor: 'Natural minor',
  harmonic_minor: 'Harmonic minor',
  pentatonic_major: 'Major pentatonic',
  pentatonic_minor: 'Minor pentatonic',
  blues: 'Blues',
  ionian: 'Ionian',
  dorian: 'Dorian',
  phrygian: 'Phrygian',
  lydian: 'Lydian',
  mixolydian: 'Mixolydian',
  aeolian: 'Aeolian',
  locrian: 'Locrian',
};

/**
 * Note names of a scale starting at `root` (a note name like `A3`), one octave,
 * root included. Flat spelling is used for roots whose major key is flat-side.
 */
export function scaleNotes(root: string, scale: ScaleId, prefer?: 'sharp' | 'flat'): string[] {
  const rootMidi = noteToMidi(root);
  const spelling = prefer ?? (FLAT_ROOTS.has(midiPitchClass(rootMidi)) ? 'flat' : 'sharp');
  return SCALES[scale].map((iv) => midiToNote(rootMidi + iv, { prefer: spelling }));
}

/** Pitch classes (0..11) of a scale for a root pitch class or MIDI number. */
export function scalePitchClasses(root: number, scale: ScaleId): number[] {
  return SCALES[scale].map((iv) => midiPitchClass(root + iv));
}

// F, B♭, E♭, A♭, D♭, G♭ — conventionally spelled with flats.
const FLAT_ROOTS = new Set([5, 10, 3, 8, 1, 6]);

export const CHORD_QUALITIES = {
  major: [0, 4, 7],
  minor: [0, 3, 7],
  diminished: [0, 3, 6],
  augmented: [0, 4, 8],
  sus2: [0, 2, 7],
  sus4: [0, 5, 7],
  major7: [0, 4, 7, 11],
  minor7: [0, 3, 7, 10],
  dominant7: [0, 4, 7, 10],
  diminished7: [0, 3, 6, 9],
  half_diminished7: [0, 3, 6, 10],
  power: [0, 7],
} as const satisfies Record<string, readonly number[]>;

export type ChordQuality = keyof typeof CHORD_QUALITIES;

/** MIDI numbers of the chord tones built on `rootMidi`. */
export function chordTones(rootMidi: number, quality: ChordQuality): number[] {
  return CHORD_QUALITIES[quality].map((iv) => rootMidi + iv);
}

/** Pitch classes (0..11) of a chord built on a root pitch class or MIDI number. */
export function chordPitchClasses(root: number, quality: ChordQuality): number[] {
  return CHORD_QUALITIES[quality].map((iv) => midiPitchClass(root + iv));
}
