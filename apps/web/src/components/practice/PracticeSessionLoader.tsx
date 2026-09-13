"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

/** The session reads localStorage on mount, so it is rendered client-side only. */
export const PracticeSessionLoader = dynamic(
  () => import("@/components/practice/PracticeSession").then((m) => m.PracticeSession),
  {
    ssr: false,
    loading: () => (
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]" aria-busy>
        <Skeleton className="h-96 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    ),
  },
);
