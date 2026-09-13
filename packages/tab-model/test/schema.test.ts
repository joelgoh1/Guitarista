import { describe, expect, it } from 'vitest';
import twinkle from './fixtures/twinkle.tab.json';
import {
  DurationSchema,
  NoteSchema,
  TabSchema,
  parseTab,
  safeParseTab,
  tabPitchRange,
  tabSummary,
  notePitch,
  durationInWholeNotes,
  validateTab,
  type Tab,
} from '../src/index.js';

describe('TabSchema', () => {
  it('accepts the twinkle fixture and applies defaults', () => {
    const tab = parseTab(twinkle);
    expect(tab.tracks).toHaveLength(1);
    expect(tab.tracks[0]!.measures).toHaveLength(2);
    // defaults
    const m2 = tab.tracks[0]!.measures[1]!;
    expect(m2.repeat_start).toBe(false);
    expect(m2.voices[0]!.beats[0]!.duration.dots).toBe(0);
    expect(m2.voices[0]!.beats[1]!.notes[0]!.tech).toEqual([]);
    expect(tab.warnings).toEqual([]);
  });

  it('rejects string index 0', () => {
    const r = NoteSchema.safeParse({ string: 0, fret: 0 });
    expect(r.success).toBe(false);
  });

  it('rejects string index above the track string count', () => {
    const bad = structuredClone(twinkle) as unknown as Tab;
    bad.tracks[0]!.measures[0]!.voices[0]!.beats[0]!.notes[0]!.string = 7;
    const r = safeParseTab(bad);
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path.at(-1) === 'string');
      expect(issue).toBeDefined();
      expect(issue!.path).toEqual(['tracks', 0, 'measures', 0, 'voices', 0, 'beats', 0, 'notes', 0, 'string']);
    }
  });

  it('rejects non-integer strings, negative frets, frets above 30', () => {
    expect(NoteSchema.safeParse({ string: 1.5, fret: 0 }).success).toBe(false);
    expect(NoteSchema.safeParse({ string: 1, fret: -1 }).success).toBe(false);
    expect(NoteSchema.safeParse({ string: 1, fret: 31 }).success).toBe(false);
    expect(NoteSchema.safeParse({ string: 1, fret: 30 }).success).toBe(true);
  });

  it('rejects unknown sources and out-of-range confidence', () => {
    expect(safeParseTab({ ...twinkle, source: 'youtube' }).success).toBe(false);
    expect(safeParseTab({ ...twinkle, confidence: 1.5 }).success).toBe(false);
  });

  it('accepts tuplets and dots', () => {
    expect(DurationSchema.parse({ num: 1, den: 8, tuplet: [3, 2] }).tuplet).toEqual([3, 2]);
    expect(durationInWholeNotes({ num: 1, den: 4, dots: 1, tuplet: null })).toBeCloseTo(0.375);
    expect(durationInWholeNotes({ num: 1, den: 8, dots: 0, tuplet: [3, 2] })).toBeCloseTo(1 / 12);
  });

  it('rejects duplicate strings within a beat and inconsistent pitch_midi (mirrors validate_tab)', () => {
    const dup = structuredClone(twinkle) as unknown as Tab;
    const beat = dup.tracks[0]!.measures[0]!.voices[0]!.beats[0]!;
    beat.notes.push({ ...beat.notes[0]!, fret: 3 });
    const r1 = safeParseTab(dup);
    expect(r1.success).toBe(false);
    if (!r1.success) expect(r1.error.issues.some((i) => /duplicate string/.test(i.message))).toBe(true);

    const wrongPitch = structuredClone(twinkle) as unknown as Tab;
    wrongPitch.tracks[0]!.measures[0]!.voices[0]!.beats[0]!.notes[0]!.pitch_midi = 61;
    const r2 = safeParseTab(wrongPitch);
    expect(r2.success).toBe(false);
    if (!r2.success) expect(r2.error.issues.some((i) => i.path.at(-1) === 'pitch_midi')).toBe(true);

    // dead notes are exempt from the pitch check
    const dead = structuredClone(twinkle) as unknown as Tab;
    const n = dead.tracks[0]!.measures[0]!.voices[0]!.beats[0]!.notes[0]!;
    n.pitch_midi = 61;
    n.dead = true;
    expect(safeParseTab(dead).success).toBe(true);
  });

  it('validateTab reports in the backend message format', () => {
    const tab = parseTab(twinkle);
    expect(validateTab(tab)).toEqual([]);
    tab.tracks[0]!.measures[1]!.voices[0]!.beats[0]!.notes[0]!.string = 9;
    expect(validateTab(tab)).toEqual(['track 0 m2 v0 b0: string 9 out of range 1..6']);
  });

  it('applies Pydantic defaults for a minimal tab', () => {
    const tab = parseTab({ id: 'x', created_at: '2026-09-11T00:00:00Z' });
    expect(tab.title).toBe('Untitled');
    expect(tab.tempo_bpm).toBe(120);
    expect(tab.time_signature).toEqual({ numerator: 4, denominator: 4 });
    expect(tab.tracks).toEqual([]);
    expect(TabSchema).toBeDefined();
  });
});

describe('helpers', () => {
  const tab = parseTab(twinkle);

  it('notePitch uses canonical string numbering (1 = highest)', () => {
    expect(notePitch({ string: 1, fret: 0 }, [64, 59, 55, 50, 45, 40])).toBe(64);
    expect(notePitch({ string: 6, fret: 0 }, [64, 59, 55, 50, 45, 40])).toBe(40);
    expect(notePitch({ string: 2, fret: 1 }, [64, 59, 55, 50, 45, 40], 2)).toBe(62);
    expect(() => notePitch({ string: 7, fret: 0 }, [64, 59, 55, 50, 45, 40])).toThrow(RangeError);
  });

  it('tabSummary', () => {
    const s = tabSummary(tab);
    expect(s.measureCount).toBe(2);
    expect(s.trackNames).toEqual(['Acoustic Guitar']);
    expect(s.noteCount).toBe(7);
    expect(s.timeSignature).toBe('4/4');
    // 8 quarter notes at 100 bpm = 4.8 s
    expect(s.durationSeconds).toBeCloseTo(4.8);
  });

  it('tabPitchRange', () => {
    // C4 (60) .. A4 (69)
    expect(tabPitchRange(tab)).toEqual({ min: 60, max: 69 });
  });
});
