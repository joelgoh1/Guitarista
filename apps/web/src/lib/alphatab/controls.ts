/**
 * Imperative helpers around AlphaTabApi. Components must not assign to the
 * api object directly (React Compiler treats context/state values as frozen),
 * so every mutation goes through these functions.
 */
import type * as alphaTab from "@coderline/alphatab";
import { getAlphaTab } from "@/lib/alphatab/loader";
import {
  applyThemeColors,
  toAlphaTabRhythmMode,
  toAlphaTabStaveProfile,
} from "@/lib/alphatab/settings";
import type { StaveProfile } from "@/lib/stores/player";

export function setPlaybackSpeed(api: alphaTab.AlphaTabApi, speed: number) {
  api.playbackSpeed = speed;
}

export function setMasterVolume(api: alphaTab.AlphaTabApi, volume: number) {
  api.masterVolume = volume;
}

export function setLooping(api: alphaTab.AlphaTabApi, loop: boolean) {
  api.isLooping = loop;
}

export function setMetronome(api: alphaTab.AlphaTabApi, on: boolean) {
  api.metronomeVolume = on ? 1 : 0;
}

export function setCountIn(api: alphaTab.AlphaTabApi, on: boolean) {
  api.countInVolume = on ? 1 : 0;
}

/** Switch stave profile in place and re-render. Returns false if unchanged. */
export function setStaveProfile(api: alphaTab.AlphaTabApi, profile: StaveProfile): boolean {
  const next = toAlphaTabStaveProfile(getAlphaTab(), profile);
  if (api.settings.display.staveProfile === next) return false;
  api.settings.display.staveProfile = next;
  api.settings.notation.rhythmMode = toAlphaTabRhythmMode(getAlphaTab(), profile);
  api.updateSettings();
  api.render();
  return true;
}

/** Re-read theme tokens and re-render (call after the `class` on <html> flips). */
export function retheme(api: alphaTab.AlphaTabApi) {
  applyThemeColors(getAlphaTab(), api.settings);
  api.updateSettings();
  api.render();
}

/**
 * Apply the playback-only capo setting. alphaTab bakes the stave capo into
 * `Note.stringTuning`, so "capo on" is the natural state (transposition 0) and
 * "capo off" plays the same frets `capo` semitones lower. Display is untouched.
 *
 * The synth resets channel transpositions whenever a MIDI is (re)generated, so
 * this must be re-applied on `midiLoaded` / `playerReady`.
 */
export function applyCapoPlayback(api: alphaTab.AlphaTabApi, capoOn: boolean) {
  for (const track of api.score?.tracks ?? []) {
    const capo = track.staves[0]?.capo ?? 0;
    if (capo <= 0) continue;
    api.changeTrackTranspositionPitch([track], capoOn ? 0 : -capo);
  }
}
