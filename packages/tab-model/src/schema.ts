/**
 * Canonical Tab JSON — mirrors the FastAPI/Pydantic domain models in
 * apps/api/src/guitarista_api/domain/tab.py (+ enums.py, validate.py).
 * Field names are snake_case because this is the wire format. Keep the two in
 * sync by hand until tab.schema.json is generated from Pydantic.
 *
 * String numbering: `Note.string` 1 = highest-pitched string (matches
 * `Track.tuning[0]`). alphaTab uses the reverse — see `alphatab-strings.ts`.
 */
import { z } from 'zod';

export const DurationSchema = z.object({
  /** Numerator of the note value, e.g. 1 for a quarter (1/4). */
  num: z.number().int().min(1),
  /** Denominator of the note value, e.g. 4 for a quarter. */
  den: z.number().int().min(1),
  dots: z.number().int().min(0).max(3).default(0),
  /** `[actual, normal]`, e.g. `[3, 2]` for a triplet. */
  tuplet: z.tuple([z.number().int().min(1), z.number().int().min(1)]).nullable().optional(),
});
export type Duration = z.infer<typeof DurationSchema>;
export type DurationInput = z.input<typeof DurationSchema>;

export const TimeSignatureSchema = z.object({
  numerator: z.number().int().min(1).default(4),
  denominator: z.number().int().min(1).default(4),
});
export type TimeSignature = z.infer<typeof TimeSignatureSchema>;

export const TAB_SOURCES = ['songsterr', 'ultimate_guitar', 'audio', 'score', 'manual'] as const;
export const TabSourceSchema = z.enum(TAB_SOURCES);
export type TabSource = z.infer<typeof TabSourceSchema>;

export const NoteSchema = z.object({
  /** 1 = highest-pitched string. */
  string: z.number().int().min(1),
  fret: z.number().int().min(0).max(30),
  /**
   * Sounding MIDI pitch if known; derivable from tuning + capo + fret otherwise.
   * When present (and the note is not dead) it must agree with tuning+capo+fret
   * — checked by `validateTab` / TrackSchema.
   */
  pitch_midi: z.number().int().nullable().optional(),
  tie: z.boolean().default(false),
  dead: z.boolean().default(false),
  ghost: z.boolean().default(false),
  /** Technique tags, e.g. `hammer`, `pull`, `slide`, `bend`, `pm`, `vibrato`. */
  tech: z.array(z.string()).default([]),
  /** 0 thumb, 1 index .. 4 pinky. */
  finger: z.number().int().min(0).max(4).nullable().optional(),
});
export type Note = z.infer<typeof NoteSchema>;
export type NoteInput = z.input<typeof NoteSchema>;

export const BeatSchema = z.object({
  duration: DurationSchema,
  /** Empty array = rest. */
  notes: z.array(NoteSchema),
  chord_name: z.string().nullable().optional(),
  text: z.string().nullable().optional(),
  tempo_bpm: z.number().positive().nullable().optional(),
});
export type Beat = z.infer<typeof BeatSchema>;
export type BeatInput = z.input<typeof BeatSchema>;

export const VoiceSchema = z.object({
  beats: z.array(BeatSchema),
});
export type Voice = z.infer<typeof VoiceSchema>;
export type VoiceInput = z.input<typeof VoiceSchema>;

export const MeasureSchema = z.object({
  /** 1-based measure number. */
  number: z.number().int().min(1),
  time_signature: TimeSignatureSchema.nullable().optional(),
  voices: z.array(VoiceSchema).default([]),
  marker: z.string().nullable().optional(),
  repeat_start: z.boolean().default(false),
  /** Repeat count when this measure closes a repeat; null/absent otherwise. */
  repeat_end: z.number().int().min(1).nullable().optional(),
});
export type Measure = z.infer<typeof MeasureSchema>;
export type MeasureInput = z.input<typeof MeasureSchema>;

export const TrackSchema = z
  .object({
    name: z.string(),
    /** GM program name or id string, e.g. `acoustic_guitar_steel`. */
    instrument: z.string(),
    /** MIDI note per string, index 0 = string 1 = highest. */
    tuning: z.array(z.number().int().min(0).max(127)).min(1),
    capo: z.number().int().min(0).default(0),
    measures: z.array(MeasureSchema).default([]),
  })
  .superRefine((track, ctx) => {
    // Structural consistency that Pydantic cannot express per-field; mirrors
    // guitarista_api.domain.validate.validate_tab.
    for (const issue of trackIssues(track)) {
      ctx.addIssue({ code: 'custom', path: issue.path, message: issue.message });
    }
  });
export type Track = z.infer<typeof TrackSchema>;
export type TrackInput = z.input<typeof TrackSchema>;

export const TabSchema = z.object({
  id: z.string().min(1),
  song_id: z.string().nullable().optional(),
  title: z.string().default('Untitled'),
  artist: z.string().nullable().optional(),
  source: TabSourceSchema.default('manual'),
  /** Provider-specific reference (Songsterr song/revision id, UG url, upload id...). */
  source_ref: z.string().nullable().optional(),
  /** 0..1 confidence in the tab's accuracy. */
  confidence: z.number().min(0).max(1).default(1),
  tempo_bpm: z.number().positive().default(120),
  time_signature: TimeSignatureSchema.default({ numerator: 4, denominator: 4 }),
  tracks: z.array(TrackSchema).default([]),
  warnings: z.array(z.string()).default([]),
  /** ISO-8601 timestamp (Pydantic datetime). */
  created_at: z.string(),
});
export type Tab = z.infer<typeof TabSchema>;
export type TabInput = z.input<typeof TabSchema>;

/** Parse (and apply defaults to) a canonical Tab JSON payload. Throws ZodError. */
export function parseTab(data: unknown): Tab {
  return TabSchema.parse(data);
}

export function safeParseTab(data: unknown): z.ZodSafeParseResult<Tab> {
  return TabSchema.safeParse(data);
}

// ---------------------------------------------------------------------------
// Consistency validation (port of domain/validate.py)
// ---------------------------------------------------------------------------

export const MAX_FRET = 30;

export interface TabIssue {
  path: (string | number)[];
  message: string;
}

type TrackLike = z.output<typeof TrackSchema> extends infer T ? Omit<T, never> : never;

function trackIssues(track: Pick<TrackLike, 'tuning' | 'capo' | 'measures'>): TabIssue[] {
  const issues: TabIssue[] = [];
  const nStrings = track.tuning.length;
  track.measures.forEach((measure, mi) => {
    measure.voices.forEach((voice, vi) => {
      voice.beats.forEach((beat, bi) => {
        const seen = new Set<number>();
        beat.notes.forEach((note, ni) => {
          const base = ['measures', mi, 'voices', vi, 'beats', bi, 'notes', ni];
          if (note.string < 1 || note.string > nStrings) {
            issues.push({ path: [...base, 'string'], message: `string ${note.string} out of range 1..${nStrings}` });
            return;
          }
          if (note.fret < 0 || note.fret > MAX_FRET) {
            issues.push({ path: [...base, 'fret'], message: `fret ${note.fret} out of range 0..${MAX_FRET}` });
          }
          if (seen.has(note.string)) {
            issues.push({ path: [...base, 'string'], message: `duplicate string ${note.string} within beat` });
          }
          seen.add(note.string);
          if (note.pitch_midi !== null && note.pitch_midi !== undefined && !note.dead) {
            const expected = track.tuning[note.string - 1]! + track.capo + note.fret;
            if (expected !== note.pitch_midi) {
              issues.push({
                path: [...base, 'pitch_midi'],
                message: `string ${note.string} fret ${note.fret} sounds ${expected}, pitch_midi says ${note.pitch_midi}`,
              });
            }
          }
        });
      });
    });
  });
  return issues;
}

/**
 * Human-readable consistency errors for an already-parsed Tab (empty when
 * valid). Same rules as the backend's `validate_tab`; `parseTab` already
 * enforces them, this is for tabs built in memory.
 */
export function validateTab(tab: Tab): string[] {
  const out: string[] = [];
  tab.tracks.forEach((track, ti) => {
    for (const issue of trackIssues(track)) {
      const [, mi, , vi, , bi] = issue.path;
      const measureNumber = track.measures[mi as number]?.number ?? mi;
      out.push(`track ${ti} m${measureNumber} v${vi} b${bi}: ${issue.message}`);
    }
  });
  return out;
}
