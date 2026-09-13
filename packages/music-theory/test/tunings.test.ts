import { describe, expect, it } from 'vitest';
import { TUNINGS, identifyTuning, tuningToNoteNames } from '../src/index.js';

describe('TUNINGS', () => {
  it('standard tuning is E4 B3 G3 D3 A2 E2 (string 1 first)', () => {
    expect(TUNINGS.standard).toEqual([64, 59, 55, 50, 45, 40]);
    expect(tuningToNoteNames(TUNINGS.standard)).toEqual(['E4', 'B3', 'G3', 'D3', 'A2', 'E2']);
  });

  it('other tunings spell as expected', () => {
    expect(tuningToNoteNames(TUNINGS.drop_d)).toEqual(['E4', 'B3', 'G3', 'D3', 'A2', 'D2']);
    expect(tuningToNoteNames(TUNINGS.half_down, 'flat')).toEqual(['E♭4', 'B♭3', 'G♭3', 'D♭3', 'A♭2', 'E♭2']);
    expect(tuningToNoteNames(TUNINGS.dadgad)).toEqual(['D4', 'A3', 'G3', 'D3', 'A2', 'D2']);
    expect(tuningToNoteNames(TUNINGS.open_g)).toEqual(['D4', 'B3', 'G3', 'D3', 'G2', 'D2']);
    expect(tuningToNoteNames(TUNINGS.bass_4)).toEqual(['G2', 'D2', 'A1', 'E1']);
    expect(tuningToNoteNames(TUNINGS.ukulele)).toEqual(['A4', 'E4', 'C4', 'G4']);
  });

  it('every 6-string tuning is descending except re-entrant ukulele', () => {
    for (const [id, t] of Object.entries(TUNINGS)) {
      if (id === 'ukulele') continue;
      for (let i = 1; i < t.length; i++) expect(t[i]!).toBeLessThan(t[i - 1]!);
    }
  });

  it('identifyTuning', () => {
    expect(identifyTuning([64, 59, 55, 50, 45, 40])).toBe('standard');
    expect(identifyTuning([64, 59, 55, 50, 45, 38])).toBe('drop_d');
    expect(identifyTuning([64, 59, 55, 50, 45, 37])).toBeUndefined();
  });
});
