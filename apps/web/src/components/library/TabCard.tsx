"use client";

import Link from "next/link";
import { Layers, Music2 } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { TabSummary } from "@/lib/api/types";
import { formatPercent, formatRelative } from "./format";
import { SourceBadge } from "./SourceBadge";

export function TabCard({ tab, now }: { tab: TabSummary; now: number }) {
  return (
    <Link
      href={`/tabs/${tab.id}`}
      className="group rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      data-testid="tab-card"
    >
      <Card className="h-full transition-colors group-hover:border-primary/40 group-hover:bg-card/80">
        <CardHeader className="gap-2">
          <div className="flex items-start justify-between gap-2">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Music2 className="size-4" aria-hidden />
            </span>
            <SourceBadge source={tab.source} />
          </div>
          <CardTitle className="truncate text-base">{tab.title}</CardTitle>
          <CardDescription className="truncate">{tab.artist ?? "Unknown artist"}</CardDescription>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Layers className="size-3" aria-hidden />
              {tab.track_count} {tab.track_count === 1 ? "track" : "tracks"}
            </span>
            <span>confidence {formatPercent(tab.confidence)}</span>
            <time dateTime={tab.created_at} className="ml-auto">
              {formatRelative(tab.created_at, now)}
            </time>
          </div>
        </CardHeader>
      </Card>
    </Link>
  );
}
