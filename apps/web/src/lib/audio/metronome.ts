import { getAudioContext } from "@/lib/audio/context";

/** Schedule a short click at `time` (AudioContext seconds). */
export function scheduleClick(time: number, accent = false, gain = 0.5) {
  const ctx = getAudioContext();
  const osc = ctx.createOscillator();
  const env = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = accent ? 1600 : 1000;
  env.gain.setValueAtTime(0.0001, time);
  env.gain.exponentialRampToValueAtTime(gain, time + 0.002);
  env.gain.exponentialRampToValueAtTime(0.0001, time + 0.06);
  osc.connect(env).connect(ctx.destination);
  osc.start(time);
  osc.stop(time + 0.08);
}
