import { z } from 'zod';
import majorChordsJson from '../data/majorChords.json';
import minorChordsJson from '../data/minorChords.json';
import { midiPitchClass, noteToMidi } from './notes';
import { STANDARD_TUNING, type Tuning } from './tunings';

// ---------------------------------------------------------------------------
// Schemas (mirror data/{major,minor}Chords.json)
// ---------------------------------------------------------------------------

export const CHORD_KEY_IDS = [
  'c',
  'c_sharp',
  'd',
  'd_sharp',
  'e',
  'f',
  'f_sharp',
  'g',
  'g_sharp',
  'a',
  'a_sharp',
  'b',
] as const;
export type ChordKeyId = (typeof CHORD_KEY_IDS)[number];
export const ChordKeyIdSchema = z.enum(CHORD_KEY_IDS);

export const CHORD_TYPE_IDS = ['major', 'minor'] as const;
export type ChordTypeId = (typeof CHORD_TYPE_IDS)[number];
export const ChordTypeIdSchema = z.enum(CHORD_TYPE_IDS);

/** A fretted/open note. `string` 1 = high E; `finger` 0 = open string. */
export const ChordPositionSchema = z.object({
  string: z.number().int().min(1).max(6),
  fret: z.number().int().min(0).max(24),
  finger: z.number().int().min(0).max(4),
});
export type ChordPosition = z.infer<typeof ChordPositionSchema>;

export const ChordBarSchema = z.object({
  hasBar: z.boolean(),
  /** First string covered by the barre (1 = high E). 0 when no barre. */
  top: z.number().int().min(0).max(6),
  /** Last string covered by the barre. 0 when no barre. */
  bottom: z.number().int().min(0).max(6),
  fret: z.number().int().min(0).max(24),
});
export type ChordBar = z.infer<typeof ChordBarSchema>;

export const ChordVariationSchema = z.object({
  /** Sounding notes low→high, scientific pitch, unicode accidentals (`C♯4`). */
  notes: z.array(z.string().regex(/^[A-G](?:♯|♭)?-?\d$/u)).min(1),
  positions: z.array(ChordPositionSchema).min(1),
  bar: ChordBarSchema,
});
export type ChordVariation = z.infer<typeof ChordVariationSchema>;

export const ChordEntrySchema = z.object({
  name: z.string().min(1),
  /**
   * Declared variation count. NOTE: the source data is not consistent about this
   * (see tests) — prefer `Object.keys(entry.variations).length`.
   */
  num_variations: z.number().int().min(1),
  variations: z.record(z.string().regex(/^\d+$/u), ChordVariationSchema),
});
export type ChordEntry = z.infer<typeof ChordEntrySchema>;

export const ChordFileSchema = z.record(ChordKeyIdSchema, ChordEntrySchema);
export type ChordFile = z.infer<typeof ChordFileSchema>;

// ---------------------------------------------------------------------------
// Static metadata
// ---------------------------------------------------------------------------

export interface ChordTypeMeta {
  id: ChordTypeId;
  label: string;
  description: string;
}

export const CHORD_TYPES: readonly ChordTypeMeta[] = [
  {
    id: 'major',
    label: 'Major',
    description: 'Bright, stable triads built from a root, major third and perfect fifth.',
  },
  {
    id: 'minor',
    label: 'Minor',
    description: 'Darker triads built from a root, minor third and perfect fifth.',
  },
];

export interface ChordKeyMeta {
  id: ChordKeyId;
  /** Display label, sharp spelling (`C♯`). */
  label: string;
  /** Enharmonic flat spelling where applicable (`D♭`). */
  flatLabel?: string;
  pitchClass: number;
}

export const CHORD_KEYS: readonly ChordKeyMeta[] = [
  { id: 'c', label: 'C', pitchClass: 0 },
  { id: 'c_sharp', label: 'C♯', flatLabel: 'D♭', pitchClass: 1 },
  { id: 'd', label: 'D', pitchClass: 2 },
  { id: 'd_sharp', label: 'D♯', flatLabel: 'E♭', pitchClass: 3 },
  { id: 'e', label: 'E', pitchClass: 4 },
  { id: 'f', label: 'F', pitchClass: 5 },
  { id: 'f_sharp', label: 'F♯', flatLabel: 'G♭', pitchClass: 6 },
  { id: 'g', label: 'G', pitchClass: 7 },
  { id: 'g_sharp', label: 'G♯', flatLabel: 'A♭', pitchClass: 8 },
  { id: 'a', label: 'A', pitchClass: 9 },
  { id: 'a_sharp', label: 'A♯', flatLabel: 'B♭', pitchClass: 10 },
  { id: 'b', label: 'B', pitchClass: 11 },
];

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

const RAW_FILES: Record<ChordTypeId, unknown> = {
  major: majorChordsJson,
  minor: minorChordsJson,
};

const cache = new Map<ChordTypeId, ChordFile>();

/** Validate and return the chord file for a type. Throws ZodError on bad data. */
export function loadChordFile(type: ChordTypeId): ChordFile {
  const cached = cache.get(type);
  if (cached) return cached;
  const parsed = ChordFileSchema.parse(RAW_FILES[type]);
  cache.set(type, parsed);
  return parsed;
}

export function getChord(type: ChordTypeId, key: ChordKeyId): ChordEntry {
  const entry = loadChordFile(type)[key];
  if (!entry) throw new Error(`No ${type} chord data for key "${key}"`);
  return entry;
}

export interface FlatChord {
  type: ChordTypeId;
  key: ChordKeyId;
  entry: ChordEntry;
}

export function getAllChords(): FlatChord[] {
  const out: FlatChord[] = [];
  for (const type of CHORD_TYPE_IDS) {
    const file = loadChordFile(type);
    for (const key of CHORD_KEY_IDS) {
      const entry = file[key];
      if (entry) out.push({ type, key, entry });
    }
  }
  return out;
}

/** Variations of an entry in numeric order. */
export function variationList(entry: ChordEntry): ChordVariation[] {
  return Object.keys(entry.variations)
    .sort((a, b) => Number(a) - Number(b))
    .map((k) => entry.variations[k]!);
}

// ---------------------------------------------------------------------------
// Pitch helpers
// ---------------------------------------------------------------------------

/** MIDI pitches sounded by a variation, ordered low→high (string 6 → string 1). */
export function variationToMidi(variation: ChordVariation, tuning: Tuning = STANDARD_TUNING): number[] {
  return [...variation.positions]
    .sort((a, b) => b.string - a.string)
    .map((p) => {
      const open = tuning[p.string - 1];
      if (open === undefined) {
        throw new Error(`Position on string ${p.string} but tuning has ${tuning.length} strings`);
      }
      return open + p.fret;
    });
}

/** MIDI pitches from the variation's `notes` field. */
export function variationNotesToMidi(variation: ChordVariation): number[] {
  return variation.notes.map(noteToMidi);
}

export function variationHasBarre(variation: ChordVariation): boolean {
  return variation.bar.hasBar;
}

/** Lowest fretted (non-open) fret, or 0 if all open. */
export function variationBaseFret(variation: ChordVariation): number {
  const fretted = variation.positions.filter((p) => p.fret > 0).map((p) => p.fret);
  return fretted.length ? Math.min(...fretted) : 0;
}

/** Strings (1 = high E) not sounded in the variation. */
export function variationMutedStrings(variation: ChordVariation, numStrings = 6): number[] {
  const used = new Set(variation.positions.map((p) => p.string));
  const out: number[] = [];
  for (let s = 1; s <= numStrings; s++) if (!used.has(s)) out.push(s);
  return out;
}

export function pitchClassSet(midis: readonly number[]): Set<number> {
  return new Set(midis.map(midiPitchClass));
}
