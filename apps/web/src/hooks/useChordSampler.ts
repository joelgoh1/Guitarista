"use client";

import * as React from "react";
import {
  block,
  getSamplerState,
  stop as stopSampler,
  strum,
  subscribeSampler,
  type SamplerState,
  type StrumOptions,
} from "@/lib/audio/chordSampler";

const SERVER_SNAPSHOT: SamplerState = {
  ready: false,
  loading: false,
  error: null,
  instrument: "acoustic_guitar_steel",
};

export function useChordSampler() {
  const state = React.useSyncExternalStore(
    subscribeSampler,
    getSamplerState,
    () => SERVER_SNAPSHOT,
  );

  const play = React.useCallback(
    (midiNotes: readonly number[], opts?: StrumOptions) =>
      strum(midiNotes, opts).catch(() => {
        /* surfaced through state.error */
      }),
    [],
  );
  const playBlock = React.useCallback(
    (midiNotes: readonly number[]) =>
      block(midiNotes).catch(() => {
        /* surfaced through state.error */
      }),
    [],
  );
  const stop = React.useCallback(() => stopSampler(), []);

  return { ready: state.ready, loading: state.loading, error: state.error, play, playBlock, stop };
}
