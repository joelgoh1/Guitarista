"use client";

import * as React from "react";
import type * as alphaTab from "@coderline/alphatab";
import { usePlayerApi } from "@/lib/alphatab/context";
import { usePlayerStore } from "@/lib/stores/player";
import { readProgress, writeProgress } from "@/lib/db";

const SAVE_INTERVAL_MS = 2000;

/** Plain functions (not hooks) so the React Compiler immutability rule is not tripped. */
function applySpeed(api: alphaTab.AlphaTabApi, speed: number) {
  api.playbackSpeed = speed;
}
function applyPosition(api: alphaTab.AlphaTabApi, ms: number) {
  try {
    api.timePosition = ms;
  } catch {
    // player may not be ready yet; position restore is best-effort
  }
}

/**
 * Persists last position + speed for a tab in Dexie and restores them once the
 * player is ready. Must render inside <PlayerApiProvider>.
 */
export function useTabProgress(tabId: string) {
  const api = usePlayerApi();
  const restoredFor = React.useRef<string | null>(null);

  // Restore once per (tab, api) when the soundfont/player is ready.
  const soundFontLoaded = usePlayerStore((s) => s.soundFontLoaded);
  const playerState = usePlayerStore((s) => s.state);
  React.useEffect(() => {
    if (!api || !soundFontLoaded || playerState === "loading" || playerState === "error") return;
    if (restoredFor.current === tabId) return;
    restoredFor.current = tabId;
    let cancelled = false;
    void readProgress(tabId).then((row) => {
      if (cancelled || !row) return;
      const store = usePlayerStore.getState();
      if (row.speed && row.speed !== store.speed) {
        applySpeed(api, row.speed);
        store.setSpeed(row.speed);
      }
      if (row.lastPositionMs > 0) applyPosition(api, row.lastPositionMs);
    });
    return () => {
      cancelled = true;
    };
  }, [api, tabId, soundFontLoaded, playerState]);

  // Save periodically while position/speed change, and on unmount.
  React.useEffect(() => {
    let last = { positionMs: -1, speed: -1 };
    let dirty = false;
    const flush = () => {
      if (!dirty) return;
      dirty = false;
      void writeProgress({ tabId, lastPositionMs: last.positionMs, speed: last.speed });
    };
    const unsub = usePlayerStore.subscribe((s) => {
      if (s.state === "idle" || s.state === "loading") return;
      if (s.positionMs !== last.positionMs || s.speed !== last.speed) {
        last = { positionMs: s.positionMs, speed: s.speed };
        dirty = true;
      }
    });
    const timer = setInterval(flush, SAVE_INTERVAL_MS);
    return () => {
      clearInterval(timer);
      unsub();
      flush();
    };
  }, [tabId]);
}
