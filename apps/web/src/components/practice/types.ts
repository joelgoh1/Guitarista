import type { ChordKeyId, ChordTypeId } from "@guitarista/music-theory";

export interface ProgressionStep {
  id: string;
  type: ChordTypeId;
  key: ChordKeyId;
  /** 0-based voicing index. */
  variation: number;
  /** 1–8 beats. */
  beats: number;
}

export interface PracticeSessionState {
  steps: ProgressionStep[];
  bpm: number;
  metronome: boolean;
}

export const STORAGE_KEY = "guitarista.practice.session.v1";

export const DEFAULT_SESSION: PracticeSessionState = {
  steps: [
    { id: "g", type: "major", key: "g", variation: 0, beats: 4 },
    { id: "d", type: "major", key: "d", variation: 0, beats: 4 },
    { id: "em", type: "minor", key: "e", variation: 0, beats: 4 },
    { id: "c", type: "major", key: "c", variation: 0, beats: 4 },
  ],
  bpm: 80,
  metronome: true,
};

export function loadSession(): PracticeSessionState | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PracticeSessionState>;
    if (!Array.isArray(parsed.steps)) return null;
    return {
      steps: parsed.steps,
      bpm: typeof parsed.bpm === "number" ? parsed.bpm : DEFAULT_SESSION.bpm,
      metronome: parsed.metronome ?? true,
    };
  } catch {
    return null;
  }
}

export function saveSession(s: PracticeSessionState) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable (private mode, quota) */
  }
}
