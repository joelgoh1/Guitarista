/**
 * PIN TEST: which way does alphaTab number strings?
 *
 * The Python alphaTex exporter (apps/api) writes canonical string indexes
 * (1 = highest) into alphaTex, and the web app reads `Note.string` back from
 * alphaTab's model (cursor / click events). This test loads real alphaTab in
 * node and pins both conventions so an alphaTab upgrade cannot silently flip them.
 *
 * RESULT (alphaTab 1.8.4):
 *  - alphaTex TEXT `fret.string.duration`: string 1 = HIGHEST.
 *      `\tuning e4 b3 g3 d3 a2 e2 . 0.1.4` sounds MIDI 64 (E4), NOT 40.
 *      => exporter emits canonical string numbers unchanged.
 *  - alphaTab MODEL `Note.string`: string 1 = LOWEST (the importer flips).
 *      The note written as `0.1.4` has model `string === 6`; `0.6.4` has
 *      model `string === 1` and realValue 40 (E2).
 *      => `toAlphaTabString(s, n) = n - s + 1` applies to model indexes only.
 */
import { describe, expect, it } from 'vitest';
import * as alphaTab from '@coderline/alphatab';
import { fromAlphaTabString, toAlphaTabString, toAlphaTexString } from '../src/index.js';

const STANDARD = [64, 59, 55, 50, 45, 40];

function firstNote(tex: string) {
  const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex);
  const staff = score.tracks[0]!.staves[0]!;
  return { staff, note: staff.bars[0]!.voices[0]!.beats[0]!.notes[0]! };
}

describe('alphaTab string numbering (pinned, alphaTab 1.8.4)', () => {
  it('model Staff.tuning is stored highest-first like Track.tuning', () => {
    const { staff } = firstNote('\\tuning e4 b3 g3 d3 a2 e2 . 0.1.4');
    expect(staff.tuning).toEqual(STANDARD);
  });

  it('alphaTex TEXT string 1 is the HIGHEST string (0.1.4 sounds E4 = 64, not 40)', () => {
    const { note } = firstNote('\\tuning e4 b3 g3 d3 a2 e2 . 0.1.4');
    expect(note.realValue).toBe(64);
    expect(note.realValue).not.toBe(40);
  });

  it('alphaTex TEXT string 6 is the LOWEST string (0.6.4 sounds E2 = 40)', () => {
    const { note } = firstNote('\\tuning e4 b3 g3 d3 a2 e2 . 0.6.4');
    expect(note.realValue).toBe(40);
  });

  it('alphaTab MODEL Note.string is 1 = LOWEST (importer flips tex index)', () => {
    expect(firstNote('\\tuning e4 b3 g3 d3 a2 e2 . 0.1.4').note.string).toBe(6);
    expect(firstNote('\\tuning e4 b3 g3 d3 a2 e2 . 0.6.4').note.string).toBe(1);
  });

  it('canonical string numbers can be written to alphaTex unchanged', () => {
    for (let canonical = 1; canonical <= 6; canonical++) {
      const texString = toAlphaTexString(canonical, 6);
      expect(texString).toBe(canonical);
      const { note } = firstNote(`\\tuning e4 b3 g3 d3 a2 e2 . 3.${texString}.4`);
      expect(note.realValue, `canonical string ${canonical}`).toBe(STANDARD[canonical - 1]! + 3);
      // and the model index we get back is the flipped one
      expect(note.string).toBe(toAlphaTabString(canonical, 6));
      expect(fromAlphaTabString(note.string, 6)).toBe(canonical);
    }
  });

  it('holds for a 4-string bass too', () => {
    const { note: hi } = firstNote('\\tuning g2 d2 a1 e1 . 0.1.4');
    const { note: lo } = firstNote('\\tuning g2 d2 a1 e1 . 0.4.4');
    expect(hi.realValue).toBe(43);
    expect(hi.string).toBe(4);
    expect(lo.realValue).toBe(28);
    expect(lo.string).toBe(1);
  });

  it('toAlphaTabString / fromAlphaTabString are inverse and range-checked', () => {
    expect(toAlphaTabString(1, 6)).toBe(6);
    expect(toAlphaTabString(6, 6)).toBe(1);
    expect(toAlphaTabString(1, 4)).toBe(4);
    for (let s = 1; s <= 6; s++) expect(fromAlphaTabString(toAlphaTabString(s, 6), 6)).toBe(s);
    expect(() => toAlphaTabString(0, 6)).toThrow(RangeError);
    expect(() => toAlphaTabString(7, 6)).toThrow(RangeError);
    expect(() => toAlphaTexString(7, 6)).toThrow(RangeError);
  });
});
