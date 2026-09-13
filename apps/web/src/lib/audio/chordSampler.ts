import { Soundfont } from "smplr";
import { getAudioContext } from "@/lib/audio/context";

export type GuitarInstrument = "acoustic_guitar_steel" | "acoustic_guitar_nylon";

export interface StrumOptions {
  /** Delay between consecutive strings in ms. */
  spreadMs?: number;
  /** `down` = low → high strings. */
  direction?: "down" | "up";
  /** Note length in seconds. */
  durationSec?: number;
  velocity?: number;
}

export interface SamplerState {
  ready: boolean;
  loading: boolean;
  error: string | null;
  instrument: GuitarInstrument;
}

let state: SamplerState = {
  ready: false,
  loading: false,
  error: null,
  instrument: "acoustic_guitar_steel",
};
let soundfont: Soundfont | null = null;
let loadPromise: Promise<Soundfont> | null = null;
const listeners = new Set<() => void>();

function setState(patch: Partial<SamplerState>) {
  state = { ...state, ...patch };
  for (const l of listeners) l();
}

export function getSamplerState() {
  return state;
}

export function subscribeSampler(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Load (or return) the soundfont. Must first be called from a user gesture. */
export function ensureSampler(): Promise<Soundfont> {
  if (soundfont) return Promise.resolve(soundfont);
  if (loadPromise) return loadPromise;
  setState({ loading: true, error: null });
  const ctx = getAudioContext();
  const sf = new Soundfont(ctx, { instrument: state.instrument, kit: "FluidR3_GM" });
  loadPromise = sf
    .load.then(() => {
      soundfont = sf;
      setState({ ready: true, loading: false });
      return sf;
    })
    .catch((err: unknown) => {
      loadPromise = null;
      setState({ loading: false, error: err instanceof Error ? err.message : String(err) });
      throw err;
    });
  return loadPromise;
}

export async function strum(midiNotes: readonly number[], opts: StrumOptions = {}) {
  const { spreadMs = 40, direction = "down", durationSec = 2.2, velocity = 96 } = opts;
  const sf = await ensureSampler();
  const now = sf.context.currentTime;
  const order = direction === "down" ? [...midiNotes] : [...midiNotes].reverse();
  order.forEach((note, i) => {
    sf.start({ note, time: now + (i * spreadMs) / 1000, duration: durationSec, velocity });
  });
}

export async function block(midiNotes: readonly number[], durationSec = 2.2) {
  return strum(midiNotes, { spreadMs: 0, durationSec });
}

export function stop() {
  soundfont?.stop();
}

/** Switch instrument; the next play call reloads the soundfont. */
export function setInstrument(instrument: GuitarInstrument) {
  if (instrument === state.instrument) return;
  soundfont?.stop();
  soundfont?.disconnect();
  soundfont = null;
  loadPromise = null;
  setState({ instrument, ready: false });
}
