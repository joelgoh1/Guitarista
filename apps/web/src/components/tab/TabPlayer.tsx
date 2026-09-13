"use client";

import * as React from "react";
import { PlayerApiProvider } from "@/lib/alphatab/context";
import TabViewer, { type TabSource } from "@/components/tab/TabViewer";
import { TabTransport } from "@/components/tab/TabTransport";
import { usePlayerStore } from "@/lib/stores/player";
import { cn } from "@/lib/utils";

export interface TabPlayerProps {
  source: TabSource;
  className?: string;
}

function ViewerWithProfile({ source }: { source: TabSource }) {
  const staveProfile = usePlayerStore((s) => s.staveProfile);
  return <TabViewer source={source} staveProfile={staveProfile} className="flex-1" />;
}

/** Full-bleed tab viewer with the transport docked at the bottom. */
export function TabPlayer({ source, className }: TabPlayerProps) {
  return (
    <PlayerApiProvider>
      <div className={cn("flex h-full min-h-0 flex-col", className)}>
        <ViewerWithProfile source={source} />
        <TabTransport className="sticky bottom-0 z-10" />
      </div>
    </PlayerApiProvider>
  );
}
