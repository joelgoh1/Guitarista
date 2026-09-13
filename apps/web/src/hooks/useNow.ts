"use client";

import * as React from "react";

/** Ticking clock (ms since epoch); `null` interval pauses it. */
export function useNow(intervalMs: number | null = 1000): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (intervalMs === null) return;
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}
