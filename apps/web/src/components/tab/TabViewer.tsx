"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import type { TabViewerProps } from "@/components/tab/types";

export type { TabSource, TabViewerProps } from "@/components/tab/types";

function TabViewerLoading() {
  return (
    <div className="flex h-full min-h-[24rem] flex-col gap-6 p-8" aria-busy="true">
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-5/6" />
    </div>
  );
}

/**
 * alphaTab touches `window`/`document` at import time, so the real viewer is
 * loaded client-side only.
 */
const TabViewer = dynamic<TabViewerProps>(() => import("./TabViewer.client"), {
  ssr: false,
  loading: TabViewerLoading,
});

export default TabViewer;
