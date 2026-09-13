"use client";

import * as React from "react";
import type * as alphaTab from "@coderline/alphatab";

export type PlayerApi = alphaTab.AlphaTabApi;

interface PlayerApiContextValue {
  api: PlayerApi | null;
  setApi: (api: PlayerApi | null) => void;
}

const PlayerApiContext = React.createContext<PlayerApiContextValue | null>(null);

/**
 * Holds the live `AlphaTabApi` instance so siblings of the viewer (e.g. the
 * transport bar) can drive it. Kept out of zustand on purpose: the API owns
 * DOM and a worker and must not be serialised or compared structurally.
 */
export function PlayerApiProvider({ children }: { children: React.ReactNode }) {
  const [api, setApi] = React.useState<PlayerApi | null>(null);
  const value = React.useMemo(() => ({ api, setApi }), [api]);
  return <PlayerApiContext.Provider value={value}>{children}</PlayerApiContext.Provider>;
}

export function usePlayerApi(): PlayerApi | null {
  const ctx = React.useContext(PlayerApiContext);
  return ctx?.api ?? null;
}

/** Internal: used by TabViewer.client to register/unregister the instance. */
export function usePlayerApiRegistrar(): PlayerApiContextValue["setApi"] {
  const ctx = React.useContext(PlayerApiContext);
  if (!ctx) {
    throw new Error("TabViewer must be rendered inside <PlayerApiProvider>");
  }
  return ctx.setApi;
}
