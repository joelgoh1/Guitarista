import { create } from "zustand";

export type PlayerLifecycle = "idle" | "loading" | "ready" | "playing" | "paused" | "error";
export type StaveProfile = "tab" | "scoreTab";

export interface TrackInfo {
  index: number;
  name: string;
  isMute: boolean;
  isSolo: boolean;
  /** Whether the track is part of `api.renderTracks`. */
  visible: boolean;
  /** Capo fret of the track's first stave (0 = none). */
  capo: number;
}

export interface PlayerState {
  state: PlayerLifecycle;
  /** Whether the soundfont finished loading (playback possible). */
  soundFontLoaded: boolean;
  positionMs: number;
  durationMs: number;
  /** Playback speed multiplier (0.5 .. 1.5). */
  speed: number;
  loop: boolean;
  tracks: TrackInfo[];
  /** 0..1 */
  masterVolume: number;
  metronome: boolean;
  countIn: boolean;
  /**
   * Playback-only capo switch. `true` plays the tab as written (the capo is
   * part of alphaTab's tuning); `false` plays the same frets `capo` semitones
   * lower, as if the capo were taken off. Never affects what is displayed.
   */
  capoOn: boolean;
  staveProfile: StaveProfile;
  title: string | null;
  artist: string | null;
  error: string | null;
}

export interface PlayerActions {
  setState: (state: PlayerLifecycle) => void;
  setSoundFontLoaded: (loaded: boolean) => void;
  setPosition: (positionMs: number, durationMs: number) => void;
  setSpeed: (speed: number) => void;
  setLoop: (loop: boolean) => void;
  setTracks: (tracks: TrackInfo[]) => void;
  updateTrack: (index: number, patch: Partial<Omit<TrackInfo, "index">>) => void;
  setMasterVolume: (volume: number) => void;
  setMetronome: (on: boolean) => void;
  setCountIn: (on: boolean) => void;
  setCapoOn: (on: boolean) => void;
  setStaveProfile: (profile: StaveProfile) => void;
  setScoreMeta: (meta: { title: string | null; artist: string | null }) => void;
  setError: (message: string | null) => void;
  reset: () => void;
}

const initialState: PlayerState = {
  state: "idle",
  soundFontLoaded: false,
  positionMs: 0,
  durationMs: 0,
  speed: 1,
  loop: false,
  tracks: [],
  masterVolume: 1,
  metronome: false,
  countIn: false,
  capoOn: true,
  staveProfile: "tab",
  title: null,
  artist: null,
  error: null,
};

/**
 * Transport state mirrored from alphaTab. The `AlphaTabApi` instance itself is
 * NOT stored here (it is not serialisable and owns DOM); see PlayerApiProvider.
 */
export const usePlayerStore = create<PlayerState & PlayerActions>()((set) => ({
  ...initialState,
  setState: (state) => set({ state }),
  setSoundFontLoaded: (soundFontLoaded) => set({ soundFontLoaded }),
  setPosition: (positionMs, durationMs) => set({ positionMs, durationMs }),
  setSpeed: (speed) => set({ speed }),
  setLoop: (loop) => set({ loop }),
  setTracks: (tracks) => set({ tracks }),
  updateTrack: (index, patch) =>
    set((s) => ({
      tracks: s.tracks.map((t) => (t.index === index ? { ...t, ...patch } : t)),
    })),
  setMasterVolume: (masterVolume) => set({ masterVolume }),
  setMetronome: (metronome) => set({ metronome }),
  setCountIn: (countIn) => set({ countIn }),
  setCapoOn: (capoOn) => set({ capoOn }),
  setStaveProfile: (staveProfile) => set({ staveProfile }),
  setScoreMeta: ({ title, artist }) => set({ title, artist }),
  setError: (error) => set({ error, ...(error ? { state: "error" as const } : {}) }),
  reset: () => set(initialState),
}));
