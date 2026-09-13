"use client";

import * as React from "react";
import type * as alphaTab from "@coderline/alphatab";
import { cn } from "@/lib/utils";
import { buildSettings } from "@/lib/alphatab/settings";
import { loadAlphaTab, type AlphaTabModule } from "@/lib/alphatab/loader";
import * as controls from "@/lib/alphatab/controls";
import { usePlayerApiRegistrar } from "@/lib/alphatab/context";
import { usePlayerStore, type TrackInfo } from "@/lib/stores/player";
import type { TabViewerProps } from "@/components/tab/types";

const POSITION_THROTTLE_MS = 100;

function toTrackInfos(api: alphaTab.AlphaTabApi): TrackInfo[] {
  const visible = new Set(api.tracks.map((t) => t.index));
  return (api.score?.tracks ?? []).map((t) => ({
    index: t.index,
    name: t.name || `Track ${t.index + 1}`,
    isMute: t.playbackInfo.isMute,
    isSolo: t.playbackInfo.isSolo,
    visible: visible.has(t.index),
    capo: t.staves[0]?.capo ?? 0,
  }));
}

export default function TabViewerClient({
  source,
  staveProfile = "tab",
  onReady,
  onError,
  className,
}: TabViewerProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const surfaceRef = React.useRef<HTMLDivElement>(null);
  const [api, setApi] = React.useState<alphaTab.AlphaTabApi | null>(null);
  const registerApi = usePlayerApiRegistrar();

  // Keep latest callbacks without re-creating the API.
  const onReadyRef = React.useRef(onReady);
  const onErrorRef = React.useRef(onError);
  React.useEffect(() => {
    onReadyRef.current = onReady;
    onErrorRef.current = onError;
  }, [onReady, onError]);

  // 1. Create / destroy the AlphaTabApi. Idempotent under StrictMode: the
  //    cleanup destroys the instance before the effect re-runs.
  React.useEffect(() => {
    const el = surfaceRef.current;
    const scrollEl = scrollRef.current;
    if (!el || !scrollEl) return;

    const store = usePlayerStore.getState();
    store.reset();
    store.setState("loading");
    store.setStaveProfile(staveProfile);

    let cancelled = false;
    let instance: alphaTab.AlphaTabApi | null = null;
    const unsubscribers: Array<() => void> = [];

    const create = (at: AlphaTabModule) => {
      if (cancelled) return;
      const settings = buildSettings(at, { scrollElement: scrollEl, staveProfile });
      const created = new at.AlphaTabApi(el, settings);
      instance = created;
      let lastPositionEmit = 0;

      unsubscribers.push(
        created.scoreLoaded.on((score) => {
          const s = usePlayerStore.getState();
          s.setScoreMeta({ title: score.title || null, artist: score.artist || null });
          s.setTracks(toTrackInfos(created));
          s.setError(null);
        }),
        created.renderFinished.on(() => {
          const s = usePlayerStore.getState();
          if (s.state === "loading") s.setState("ready");
          // renderTracks may change which tracks are visible.
          s.setTracks(toTrackInfos(created));
          onReadyRef.current?.();
        }),
        created.soundFontLoaded.on(() => {
          usePlayerStore.getState().setSoundFontLoaded(true);
        }),
        created.playerReady.on(() => {
          const s = usePlayerStore.getState();
          s.setSoundFontLoaded(true);
          if (s.state === "loading") s.setState("ready");
          controls.applyCapoPlayback(created, s.capoOn);
        }),
        // Loading a MIDI resets the synth's channel states, wiping the live
        // transposition, so the capo setting has to be re-applied every time.
        created.midiLoaded.on(() => {
          controls.applyCapoPlayback(created, usePlayerStore.getState().capoOn);
        }),
        created.playerStateChanged.on((e) => {
          const s = usePlayerStore.getState();
          if (e.state === at.synth.PlayerState.Playing) {
            s.setState("playing");
          } else {
            s.setState(e.stopped ? "ready" : "paused");
            if (e.stopped) s.setPosition(0, s.durationMs);
          }
        }),
        created.playerPositionChanged.on((e) => {
          const now = performance.now();
          if (!e.isSeek && now - lastPositionEmit < POSITION_THROTTLE_MS) return;
          lastPositionEmit = now;
          usePlayerStore.getState().setPosition(e.currentTime, e.endTime);
        }),
        created.playerFinished.on(() => {
          const s = usePlayerStore.getState();
          if (!s.loop) s.setState("ready");
        }),
        created.error.on((err) => {
          const message = err?.message ?? String(err);
          usePlayerStore.getState().setError(message);
          onErrorRef.current?.(err instanceof Error ? err : new Error(message));
        }),
      );

      setApi(created);
      registerApi(created);
    };

    loadAlphaTab().then(create, (err: unknown) => {
      if (cancelled) return;
      const e = err instanceof Error ? err : new Error(String(err));
      usePlayerStore.getState().setError(`Failed to load alphaTab runtime: ${e.message}`);
      onErrorRef.current?.(e);
    });

    return () => {
      cancelled = true;
      for (const off of unsubscribers) off();
      registerApi(null);
      setApi(null);
      try {
        instance?.destroy();
      } catch {
        // alphaTab may throw if the worker already went away; ignore.
      }
      usePlayerStore.getState().reset();
    };
    // staveProfile changes are applied in-place below; not a reason to rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registerApi]);

  // 2. Load the source whenever it (or the API instance) changes.
  React.useEffect(() => {
    if (!api) return;
    usePlayerStore.getState().setState("loading");
    try {
      if (source.kind === "alphaTex") {
        api.tex(source.tex);
      } else if (source.kind === "url") {
        api.load(source.url);
      } else {
        api.load(source.data);
      }
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      usePlayerStore.getState().setError(e.message);
      onErrorRef.current?.(e);
    }
  }, [api, source]);

  // 3. Stave profile switch without rebuilding the API.
  React.useEffect(() => {
    if (!api) return;
    if (controls.setStaveProfile(api, staveProfile)) {
      usePlayerStore.getState().setStaveProfile(staveProfile);
    }
  }, [api, staveProfile]);

  // 4. Re-theme when the `class` on <html> flips (next-themes).
  React.useEffect(() => {
    if (!api) return;
    const observer = new MutationObserver(() => controls.retheme(api));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [api]);

  return (
    <div
      ref={scrollRef}
      data-slot="tab-viewer"
      className={cn("relative h-full min-h-0 w-full overflow-auto", className)}
    >
      <div ref={surfaceRef} className="at-surface mx-auto w-full max-w-6xl px-4 py-6" />
    </div>
  );
}
