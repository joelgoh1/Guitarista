/**
 * Shared browser AudioContext. Created lazily on first use (call it from a user
 * gesture so autoplay policy lets it start) and resumed when suspended.
 */
let ctx: AudioContext | null = null;

export function getAudioContext(): AudioContext {
  if (typeof window === "undefined") throw new Error("AudioContext requires a browser");
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

export function hasAudioContext() {
  return ctx !== null;
}
