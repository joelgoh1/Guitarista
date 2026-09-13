/**
 * String-index conventions around alphaTab — verified against
 * @coderline/alphatab 1.8.4 by test/alphatab-string-index.test.ts.
 *
 * There are TWO different conventions in alphaTab:
 *
 * 1. alphaTex TEXT (`fret.string.duration`): string 1 = HIGHEST-pitched string,
 *    exactly like conventional tablature and our canonical Tab model.
 *    `\tuning e4 b3 g3 d3 a2 e2 . 1.1.4` sounds MIDI 65 (F4).
 *    => The Python alphaTex exporter must emit canonical string numbers UNCHANGED.
 *
 * 2. alphaTab MODEL (`alphaTab.model.Note.string`, playback/cursor/click events):
 *    string 1 = LOWEST-pitched string ("1 is the lowest string on the guitar and
 *    the bottom line on the tablature" — alphaTab.d.ts). The alphaTex importer
 *    flips: tex string s becomes model string `numStrings - s + 1`.
 *    => Use `toAlphaTabString` / `fromAlphaTabString` when talking to the model.
 *
 * `Staff.tuning` in the model is stored highest-first ([64,59,55,50,45,40]),
 * same as our `Track.tuning`.
 */

/** Canonical / alphaTex (1 = highest) → alphaTab MODEL (1 = lowest). */
export function toAlphaTabString(string: number, numStrings: number): number {
  assertStringIndex(string, numStrings);
  return numStrings - string + 1;
}

/** alphaTab MODEL (1 = lowest) → canonical / alphaTex (1 = highest). Same formula. */
export function fromAlphaTabString(alphaTabString: number, numStrings: number): number {
  assertStringIndex(alphaTabString, numStrings);
  return numStrings - alphaTabString + 1;
}

/**
 * Canonical (1 = highest) → alphaTex text string number. Identity; exists so
 * call sites document that NO flip is intended for alphaTex output.
 */
export function toAlphaTexString(string: number, numStrings: number): number {
  assertStringIndex(string, numStrings);
  return string;
}

function assertStringIndex(string: number, numStrings: number): void {
  if (!Number.isInteger(string) || string < 1 || string > numStrings) {
    throw new RangeError(`string index ${string} out of range 1..${numStrings}`);
  }
}
