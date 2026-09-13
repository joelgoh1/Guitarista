import { describe, expect, it } from 'vitest';
import {
  isEnharmonic,
  midiToNote,
  normalizeNoteName,
  noteToMidi,
  parseNote,
  pitchClass,
  toAsciiAccidentals,
  toMusic21Name,
  toUnicodeAccidentals,
  transpose,
} from '../src/index.js';

describe('parseNote', () => {
  it('parses every accidental spelling', () => {
    expect(parseNote('C♯4')).toEqual({ letter: 'C', accidental: 1, octave: 4, midi: 61 });
    expect(parseNote('C#4').midi).toBe(61);
    expect(parseNote('Db3')).toEqual({ letter: 'D', accidental: -1, octave: 3, midi: 49 });
    expect(parseNote('D♭3').midi).toBe(49);
    expect(parseNote('E-2')).toEqual({ letter: 'E', accidental: -1, octave: 2, midi: 39 });
    expect(parseNote('e2').midi).toBe(40);
    expect(parseNote('C4').midi).toBe(60);
    expect(parseNote('A4').midi).toBe(69);
    // `-` is a flat (music21 style), so `C-1` is C♭1, NOT MIDI 0 / octave -1.
    expect(parseNote('C-1').midi).toBe(23);
  });

  it('rejects garbage', () => {
    expect(() => parseNote('H4')).toThrow();
    expect(() => parseNote('C')).toThrow();
    expect(() => parseNote('C##4')).toThrow();
    expect(() => parseNote('G10')).toThrow();
  });
});

describe('midiToNote / round trips', () => {
  it('round-trips every MIDI value in both spellings (octave >= 0)', () => {
    // Octave -1 (MIDI 0..11) cannot round-trip because `-` is reserved for flats.
    for (let m = 12; m <= 127; m++) {
      expect(noteToMidi(midiToNote(m))).toBe(m);
      expect(noteToMidi(midiToNote(m, { prefer: 'flat' }))).toBe(m);
    }
  });

  it('uses unicode accidentals', () => {
    expect(midiToNote(61)).toBe('C♯4');
    expect(midiToNote(61, { prefer: 'flat' })).toBe('D♭4');
    expect(midiToNote(40)).toBe('E2');
  });

  it('normalizes spellings', () => {
    expect(normalizeNoteName('db3')).toBe('D♭3');
    expect(normalizeNoteName('c#4')).toBe('C♯4');
    expect(normalizeNoteName('E-2')).toBe('E♭2');
    expect(normalizeNoteName(' G 3 ')).toBe('G3');
  });

  it('converts between unicode, ascii and music21 forms', () => {
    expect(toUnicodeAccidentals('C#4')).toBe('C♯4');
    expect(toUnicodeAccidentals('Db3')).toBe('D♭3');
    expect(toUnicodeAccidentals('E-2')).toBe('E♭2');
    expect(toAsciiAccidentals('C♯4')).toBe('C#4');
    expect(toAsciiAccidentals('D♭3')).toBe('Db3');
    expect(toMusic21Name('D♭3')).toBe('D-3');
    expect(toMusic21Name('C♯4')).toBe('C#4');
    expect(toMusic21Name('B3')).toBe('B3');
  });
});

describe('transpose / pitchClass', () => {
  it('transposes', () => {
    expect(transpose('E2', 5)).toBe('A2');
    expect(transpose('C4', -1)).toBe('B3');
    expect(transpose('A3', 1, { prefer: 'flat' })).toBe('B♭3');
  });
  it('pitch class', () => {
    expect(pitchClass('C4')).toBe(0);
    expect(pitchClass('B♭2')).toBe(10);
    expect(isEnharmonic('C♯4', 'D♭4')).toBe(true);
    expect(isEnharmonic('C♯4', 'D♭5')).toBe(false);
  });
});
