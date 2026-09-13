"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { parseAsInteger, useQueryState } from "nuqs";
import { AlertTriangle, ChevronDown, Download, ExternalLink, Layers, Music2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageContainer } from "@/components/common/PageContainer";
import TabViewer from "@/components/tab/TabViewer";
import { TabTransport } from "@/components/tab/TabTransport";
import { PlayerApiProvider } from "@/lib/alphatab/context";
import { apiUrl } from "@/lib/api/client";
import { songTabsQuery, tabAlphaTexQuery, tabQuery } from "@/lib/api/queries";
import { toApiError } from "@/lib/api/problem";
import type { Tab } from "@/lib/api/types";
import { useTabProgress } from "@/hooks/useTabProgress";
import { NextVersionButton, OtherVersionsSheet } from "@/components/song/OtherVersions";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./SourceBadge";
import { formatPercent } from "./format";

/** `songsterr:{songId}:{revisionId}:[...]` → public Songsterr URL. */
export function songsterrUrl(sourceRef: string | null | undefined): string | null {
  if (!sourceRef) return null;
  const m = /^songsterr:(\d+)/.exec(sourceRef);
  return m ? `https://www.songsterr.com/a/wsa/-s${m[1]}` : null;
}

function ProgressSaver({ tabId }: { tabId: string }) {
  useTabProgress(tabId);
  return null;
}

export function TabDetail({ tabId }: { tabId: string }) {
  const tab = useQuery(tabQuery(tabId));
  const [trackParam, setTrackParam] = useQueryState("track", parseAsInteger.withDefault(0));
  const trackCount = tab.data?.tracks?.length ?? 0;
  const track = trackCount ? Math.min(Math.max(0, trackParam), trackCount - 1) : 0;
  const tex = useQuery({ ...tabAlphaTexQuery(tabId, track), enabled: tab.isSuccess });
  const source = React.useMemo(
    () => (tex.data ? ({ kind: "alphaTex", tex: tex.data } as const) : null),
    [tex.data],
  );

  if (tab.isError) {
    const err = toApiError(tab.error);
    return (
      <PageContainer className="flex items-center">
        <EmptyState
          className="w-full"
          icon={Music2}
          title={err.status === 404 ? "Tab not found" : err.title}
          description={err.detail}
          action={
            <Button variant="secondary" nativeButton={false} render={<Link href="/library" />}>
              Back to library
            </Button>
          }
        />
      </PageContainer>
    );
  }

  return (
    <div className="flex h-[calc(100svh-3rem)] min-h-0 flex-1 flex-col" data-testid="tab-detail">
      <TabHeader tab={tab.data} tabId={tabId} track={track} onTrackChange={(t) => void setTrackParam(t)} />
      <PlayerApiProvider>
        <div className="flex min-h-0 flex-1 flex-col">
          {tex.isError ? (
            <PageContainer className="flex items-center">
              <EmptyState
                className="w-full"
                icon={AlertTriangle}
                title="Couldn't export this tab to alphaTex"
                description={toApiError(tex.error).detail}
                action={
                  <Button variant="secondary" size="sm" onClick={() => void tex.refetch()}>
                    Retry
                  </Button>
                }
              />
            </PageContainer>
          ) : source ? (
            <>
              <TabViewer key={`${tabId}:${track}`} source={source} className="flex-1" />
              <ProgressSaver tabId={tabId} />
            </>
          ) : (
            <div className="flex flex-1 flex-col gap-6 p-8" aria-busy="true">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}
          <TabTransport className="sticky bottom-0 z-10" />
        </div>
      </PlayerApiProvider>
    </div>
  );
}

interface TabHeaderProps {
  tab: Tab | undefined;
  tabId: string;
  track: number;
  onTrackChange: (track: number) => void;
}

function TabHeader({ tab, tabId, track, onTrackChange }: TabHeaderProps) {
  const [warningsOpen, setWarningsOpen] = React.useState(false);
  const [versionsOpen, setVersionsOpen] = React.useState(false);
  const songId = tab?.song_id ?? null;
  const songTabs = useQuery({ ...songTabsQuery(songId ?? ""), enabled: !!songId });
  const versionCount = songTabs.data?.length ?? 0;
  const tracks = tab?.tracks ?? [];
  const trackItems = tracks.map((t, i) => ({ value: String(i), label: t.name || `Track ${i + 1}` }));
  const songsterr = songsterrUrl(tab?.source_ref);
  const warnings = tab?.warnings ?? [];

  return (
    <header
      data-slot="tab-header"
      className="flex flex-col gap-2 border-b border-border bg-card/60 px-4 py-3 backdrop-blur sm:px-6"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          {tab ? (
            <>
              <h1 className="truncate text-lg font-semibold tracking-tight">{tab.title}</h1>
              <p className="truncate text-sm text-muted-foreground">
                {tab.artist ?? "Unknown artist"} · {tab.tempo_bpm} bpm
                {tab.time_signature ? ` · ${tab.time_signature.numerator}/${tab.time_signature.denominator}` : ""}
              </p>
            </>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-32" />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {tab ? (
            <>
              <SourceBadge source={tab.source} />
              {songId && versionCount > 1 ? (
                <button
                  type="button"
                  className={cn(badgeVariants({ variant: "secondary" }), "cursor-pointer hover:bg-muted")}
                  onClick={() => setVersionsOpen(true)}
                  title="Other stored versions of this song"
                  data-testid="version-count"
                >
                  <Layers /> {versionCount} versions
                </button>
              ) : null}
              <Badge
                variant={tab.confidence >= 0.8 ? "secondary" : "outline"}
                className={cn(tab.confidence < 0.5 && "text-warning")}
                title="Source confidence"
              >
                {formatPercent(tab.confidence)} confidence
              </Badge>
            </>
          ) : null}

          {trackItems.length > 1 ? (
            <Select
              items={trackItems}
              value={String(track)}
              onValueChange={(v) => onTrackChange(Number.parseInt(String(v), 10) || 0)}
            >
              <SelectTrigger size="sm" aria-label="Track" className="max-w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                {trackItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}

          <Button
            variant="outline"
            size="sm" nativeButton={false} render={<a href={apiUrl(`/tabs/${tabId}`, { format: "musicxml", track })} download />}
          >
            <Download data-icon="inline-start" />
            <span className="hidden sm:inline">MusicXML</span>
          </Button>
          {songsterr ? (
            <Button
              variant="ghost"
              size="sm" nativeButton={false} render={<a href={songsterr} target="_blank" rel="noreferrer noopener" />}
            >
              <ExternalLink data-icon="inline-start" />
              <span className="hidden sm:inline">Songsterr</span>
            </Button>
          ) : null}
          {tab && songId ? (
            <>
              <OtherVersionsSheet
                songId={songId}
                currentTab={tab}
                open={versionsOpen}
                onOpenChange={setVersionsOpen}
                trigger={<Button variant="outline" size="sm" />}
              >
                <Layers data-icon="inline-start" />
                <span className="hidden sm:inline">Other versions</span>
              </OtherVersionsSheet>
              <NextVersionButton songId={songId} currentTab={tab} compact />
            </>
          ) : null}
        </div>
      </div>

      {warnings.length ? (
        <div className="flex flex-col gap-1">
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="-ml-2 w-fit text-warning"
            aria-expanded={warningsOpen}
            aria-controls="tab-warnings"
            onClick={() => setWarningsOpen((o) => !o)}
          >
            <AlertTriangle data-icon="inline-start" />
            {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
            <ChevronDown data-icon="inline-end" className={cn("transition-transform", warningsOpen && "rotate-180")} />
          </Button>
          <AnimatePresence initial={false}>
            {warningsOpen ? (
              <motion.ul
                id="tab-warnings"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="list-disc overflow-hidden pl-5 text-xs text-muted-foreground"
              >
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </motion.ul>
            ) : null}
          </AnimatePresence>
        </div>
      ) : null}
    </header>
  );
}
