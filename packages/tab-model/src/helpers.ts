import type { Beat, Duration, Note, Tab, Track } from './schema';

/** Length of a duration in whole notes (a quarter = 0.25). */
export function durationInWholeNotes(d: Duration): number {
  let value = d.num / d.den;
  // Each dot adds half of the previous addition.
  let add = value;
  for (let i = 0; i < (d.dots ?? 0); i++) {
    add /= 2;
    value += add;
  }
  if (d.tuplet) {
    const [actual, normal] = d.tuplet;
    value *= normal / actual;
  }
  return value;
}

export function beatDurationSeconds(beat: Beat, bpm: number): number {
  // bpm counts quarter notes.
  return durationInWholeNotes(beat.duration) * 4 * (60 / bpm);
}

/** Sounding MIDI pitch of a note, from tuning (index 0 = string 1) and capo. */
export function notePitch(note: Pick<Note, 'string' | 'fret'>, tuning: readonly number[], capo = 0): number {
  const open = tuning[note.string - 1];
  if (open === undefined) {
    throw new RangeError(`string ${note.string} not in tuning of ${tuning.length} strings`);
  }
  return open + capo + note.fret;
}

/** Pitch of a note, honouring an explicit `pitch_midi` when present. */
export function resolveNotePitch(note: Note, track: Pick<Track, 'tuning' | 'capo'>): number {
  return note.pitch_midi ?? notePitch(note, track.tuning, track.capo);
}

export interface TabSummary {
  measureCount: number;
  trackNames: string[];
  noteCount: number;
  /** Estimated duration in seconds, following tempo changes and repeat counts. */
  durationSeconds: number;
  tempoBpm: number;
  timeSignature: string;
}

/**
 * Duration estimate for a single track: sums the longest voice of each
 * measure, applying inline `tempo_bpm` changes and `repeat_end` counts (the
 * repeated span is approximated as the measures since the last `repeat_start`).
 */
export function trackDurationSeconds(track: Track, initialBpm: number): number {
  let bpm = initialBpm;
  let total = 0;
  let repeatStartIdx = 0;
  const measureSeconds: number[] = [];

  track.measures.forEach((measure, idx) => {
    if (measure.repeat_start) repeatStartIdx = idx;
    let longest = 0;
    for (const voice of measure.voices) {
      let sum = 0;
      for (const beat of voice.beats) {
        if (beat.tempo_bpm) bpm = beat.tempo_bpm;
        sum += beatDurationSeconds(beat, bpm);
      }
      longest = Math.max(longest, sum);
    }
    measureSeconds.push(longest);
    total += longest;
    if (measure.repeat_end && measure.repeat_end > 1) {
      let span = 0;
      for (let i = repeatStartIdx; i <= idx; i++) span += measureSeconds[i] ?? 0;
      total += span * (measure.repeat_end - 1);
    }
  });
  return total;
}

export function tabSummary(tab: Tab): TabSummary {
  const measureCount = Math.max(0, ...tab.tracks.map((t) => t.measures.length));
  let noteCount = 0;
  for (const track of tab.tracks) {
    for (const m of track.measures) for (const v of m.voices) for (const b of v.beats) noteCount += b.notes.length;
  }
  const durationSeconds = Math.max(0, ...tab.tracks.map((t) => trackDurationSeconds(t, tab.tempo_bpm)));
  return {
    measureCount,
    trackNames: tab.tracks.map((t) => t.name),
    noteCount,
    durationSeconds,
    tempoBpm: tab.tempo_bpm,
    timeSignature: `${tab.time_signature.numerator}/${tab.time_signature.denominator}`,
  };
}

export interface PitchRange {
  min: number;
  max: number;
}

/** Lowest and highest sounding MIDI pitch across all tracks, or null if there are no notes. */
export function tabPitchRange(tab: Tab): PitchRange | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const track of tab.tracks) {
    for (const m of track.measures) {
      for (const v of m.voices) {
        for (const b of v.beats) {
          for (const n of b.notes) {
            if (n.dead) continue;
            const p = resolveNotePitch(n, track);
            if (p < min) min = p;
            if (p > max) max = p;
          }
        }
      }
    }
  }
  return Number.isFinite(min) ? { min, max } : null;
}

/** Iterate every note with its context. */
export function* iterateNotes(tab: Tab): Generator<{ track: Track; measureIndex: number; beat: Beat; note: Note }> {
  for (const track of tab.tracks) {
    for (const [measureIndex, m] of track.measures.entries()) {
      for (const v of m.voices) for (const beat of v.beats) for (const note of beat.notes) yield { track, measureIndex, beat, note };
    }
  }
}
