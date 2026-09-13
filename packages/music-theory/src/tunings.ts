import { midiToNote } from './notes';

/**
 * Tunings as MIDI numbers, index 0 = string 1 = highest-pitched string.
 * (This is the canonical Guitarista convention; alphaTab numbers strings the
 * other way round, see @guitarista/tab-model `toAlphaTabString`.)
 */
export type Tuning = readonly number[];

export const TUNINGS = {
  standard: [64, 59, 55, 50, 45, 40],
  drop_d: [64, 59, 55, 50, 45, 38],
  half_down: [63, 58, 54, 49, 44, 39],
  dadgad: [62, 57, 55, 50, 45, 38],
  open_g: [62, 59, 55, 50, 43, 38],
  bass_4: [43, 38, 33, 28],
  ukulele: [69, 64, 60, 67],
} as const satisfies Record<string, Tuning>;

export type TuningId = keyof typeof TUNINGS;

export const TUNING_LABELS: Record<TuningId, string> = {
  standard: 'Standard (E A D G B E)',
  drop_d: 'Drop D',
  half_down: 'Half-step down (E♭ standard)',
  dadgad: 'DADGAD',
  open_g: 'Open G',
  bass_4: 'Bass (4-string)',
  ukulele: 'Ukulele (gCEA, re-entrant)',
};

export const STANDARD_TUNING: Tuning = TUNINGS.standard;

/** Note names per string, string 1 first (highest). */
export function tuningToNoteNames(tuning: Tuning, prefer: 'sharp' | 'flat' = 'sharp'): string[] {
  return tuning.map((m) => midiToNote(m, { prefer }));
}

/** Find a named tuning matching the given MIDI array, or undefined. */
export function identifyTuning(tuning: Tuning): TuningId | undefined {
  for (const [id, t] of Object.entries(TUNINGS) as [TuningId, Tuning][]) {
    if (t.length === tuning.length && t.every((v, i) => v === tuning[i])) return id;
  }
  return undefined;
}
