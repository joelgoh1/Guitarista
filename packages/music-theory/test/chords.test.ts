import { describe, expect, it } from 'vitest';
import {
  CHORD_KEYS,
  CHORD_KEY_IDS,
  CHORD_TYPES,
  ChordFileSchema,
  TUNINGS,
  getAllChords,
  getChord,
  loadChordFile,
  midiToNote,
  pitchClassSet,
  variationHasBarre,
  variationList,
  variationNotesToMidi,
  variationToMidi,
  type ChordKeyId,
  type ChordTypeId,
} from '../src/index.js';
import majorRaw from '../data/majorChords.json';
import minorRaw from '../data/minorChords.json';

/**
 * Entries whose `notes` field is known to disagree with the pitches implied by
 * `positions`. Key format: `${type}/${key}/${variation}`. Anything listed here
 * is still reported, but does not fail the suite. Keep this list EMPTY unless
 * the data has been reviewed and the discrepancy accepted.
 */
const KNOWN_BAD_PITCH_ENTRIES = new Set<string>([]);

/**
 * Variations whose sounded pitches do not form the triad of their key/type.
 * These are major voicings copy-pasted into the minor file (positions AND notes
 * are identical to the corresponding major entries). `num_variations: 1` on
 * those entries suggests only variation 1 was ever intended to be shown.
 */
const KNOWN_WRONG_QUALITY = new Set<string>([]);

/** Entries whose declared `num_variations` differs from the actual count. */
const KNOWN_BAD_VARIATION_COUNTS = new Set<string>([]);

describe('chord files', () => {
  it('both JSON files validate against ChordFileSchema', () => {
    expect(() => ChordFileSchema.parse(majorRaw)).not.toThrow();
    expect(() => ChordFileSchema.parse(minorRaw)).not.toThrow();
  });

  it('loadChordFile returns all 12 keys per type', () => {
    for (const { id } of CHORD_TYPES) {
      const file = loadChordFile(id);
      expect(Object.keys(file).sort()).toEqual([...CHORD_KEY_IDS].sort());
    }
  });

  it('CHORD_KEYS covers CHORD_KEY_IDS in order with correct pitch classes', () => {
    expect(CHORD_KEYS.map((k) => k.id)).toEqual([...CHORD_KEY_IDS]);
    CHORD_KEYS.forEach((k, i) => expect(k.pitchClass).toBe(i));
  });

  it('getChord name matches key label + type', () => {
    for (const { id: type } of CHORD_TYPES) {
      for (const key of CHORD_KEYS) {
        expect(getChord(type, key.id).name).toBe(`${key.label} ${type}`);
      }
    }
  });

  it('getAllChords is flattened over types x keys', () => {
    const all = getAllChords();
    expect(all).toHaveLength(CHORD_TYPES.length * CHORD_KEY_IDS.length);
  });

  it('num_variations matches actual variation count (except allowlisted)', () => {
    const mismatches: string[] = [];
    for (const { type, key, entry } of getAllChords()) {
      const actual = Object.keys(entry.variations).length;
      if (actual !== entry.num_variations) {
        const id = `${type}/${key}`;
        if (!KNOWN_BAD_VARIATION_COUNTS.has(id)) {
          mismatches.push(`${id}: num_variations=${entry.num_variations}, actual=${actual}`);
        }
      }
    }
    expect(mismatches, mismatches.join('\n')).toEqual([]);
  });

  it('every variation: notes pitch-class set == positions pitch-class set (standard tuning)', () => {
    const failures: string[] = [];
    for (const { type, key, entry } of getAllChords()) {
      for (const [vid, variation] of Object.entries(entry.variations)) {
        const fromNotes = pitchClassSet(variationNotesToMidi(variation));
        const fromPositions = pitchClassSet(variationToMidi(variation, TUNINGS.standard));
        const same =
          fromNotes.size === fromPositions.size && [...fromNotes].every((pc) => fromPositions.has(pc));
        if (!same) {
          const id = `${type}/${key}/${vid}`;
          const msg = `${id}: notes=[${variation.notes.join(' ')}] positions→[${variationToMidi(variation)
            .map((m) => midiToNote(m))
            .join(' ')}]`;
          if (!KNOWN_BAD_PITCH_ENTRIES.has(id)) failures.push(msg);
        }
      }
    }
    expect(failures, `Pitch-class mismatches:\n${failures.join('\n')}`).toEqual([]);
  });

  it('every variation: exact MIDI multiset from notes equals positions (strict, reported)', () => {
    // Stricter than pitch-class equality: octaves must match too.
    const failures: string[] = [];
    for (const { type, key, entry } of getAllChords()) {
      for (const [vid, variation] of Object.entries(entry.variations)) {
        const a = [...variationNotesToMidi(variation)].sort((x, y) => x - y);
        const b = [...variationToMidi(variation)].sort((x, y) => x - y);
        if (a.length !== b.length || a.some((v, i) => v !== b[i])) {
          const id = `${type}/${key}/${vid}`;
          if (!KNOWN_BAD_PITCH_ENTRIES.has(id)) {
            failures.push(`${id}: notes=[${a.map((m) => midiToNote(m)).join(' ')}] positions=[${b.map((m) => midiToNote(m)).join(' ')}]`);
          }
        }
      }
    }
    expect(failures, `Exact-pitch mismatches:\n${failures.join('\n')}`).toEqual([]);
  });

  it('every variation contains the root pitch class of its key', () => {
    const failures: string[] = [];
    for (const { type, key, entry } of getAllChords()) {
      const root = CHORD_KEYS.find((k) => k.id === key)!.pitchClass;
      const third = type === 'major' ? (root + 4) % 12 : (root + 3) % 12;
      const fifth = (root + 7) % 12;
      for (const [vid, variation] of Object.entries(entry.variations)) {
        const pcs = pitchClassSet(variationToMidi(variation));
        const expected = new Set([root, third, fifth]);
        const ok = pcs.size === 3 && [...expected].every((pc) => pcs.has(pc));
        const id = `${type}/${key}/${vid}`;
        if (!ok && !KNOWN_WRONG_QUALITY.has(id)) failures.push(`${id}: pcs=${[...pcs].sort((x, y) => x - y).join(',')}`);
      }
    }
    expect(failures, `Triad mismatches:\n${failures.join('\n')}`).toEqual([]);
  });

  it('bar descriptors are self-consistent and one position per string', () => {
    for (const { type, key, entry } of getAllChords()) {
      for (const [vid, v] of Object.entries(entry.variations)) {
        const id = `${type}/${key}/${vid}`;
        const strings = v.positions.map((p) => p.string);
        expect(new Set(strings).size, `${id}: duplicate string`).toBe(strings.length);
        if (variationHasBarre(v)) {
          expect(v.bar.fret, `${id}: barre fret`).toBeGreaterThan(0);
          expect(v.bar.top, `${id}: barre top`).toBeGreaterThanOrEqual(1);
          expect(v.bar.bottom, `${id}: barre bottom`).toBeGreaterThanOrEqual(v.bar.top);
          // Every string inside the barre span must be fretted at >= barre fret.
          for (const p of v.positions) {
            if (p.string >= v.bar.top && p.string <= v.bar.bottom) {
              expect(p.fret, `${id}: string ${p.string} below barre`).toBeGreaterThanOrEqual(v.bar.fret);
            }
          }
        }
      }
    }
  });

  it('variationList orders numerically', () => {
    const c = getChord('major', 'c');
    expect(variationList(c)).toHaveLength(3);
    expect(variationList(c)[0]).toBe(c.variations['1']);
  });

  it('variationToMidi computes the open C chord', () => {
    const c = getChord('major' satisfies ChordTypeId, 'c' satisfies ChordKeyId).variations['1']!;
    expect(variationToMidi(c).map((m) => midiToNote(m))).toEqual(['C3', 'E3', 'G3', 'C4', 'E4']);
  });
});
