"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ChevronDown, Download, ExternalLink, Layers, Loader2, RotateCcw, SkipForward, Star, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { candidatesQuery, useCreateJob } from "@/lib/api/queries";
import { toApiError } from "@/lib/api/problem";
import type { Candidate, CandidateRef } from "@/lib/api/types";
import { sourceLabel } from "@/components/library/SourceBadge";
import { cn } from "@/lib/utils";
import {
  clearExclusions,
  computeExclusions,
  groupCandidates,
  isCurrentCandidate,
  loadExclusions,
  mergeRefs,
  saveExclusions,
  scorePercent,
  type CurrentTabRef,
} from "./versions";

// ---------------------------------------------------------------------------
// "Not this one, next"
// ---------------------------------------------------------------------------

export interface UseNextVersionOptions {
  songId: string | null | undefined;
  currentTab?: CurrentTabRef | null;
}

/**
 * Starts a job that skips every version already tried for this song. The
 * exclusion list is remembered per song in sessionStorage so repeated clicks
 * keep walking Songsterr → Ultimate Guitar → audio.
 */
export function useNextVersion({ songId, currentTab }: UseNextVersionOptions) {
  const router = useRouter();
  const qc = useQueryClient();
  const createJob = useCreateJob();
  const [loadingCandidates, setLoadingCandidates] = React.useState(false);
  // sessionStorage is guarded (SSR → []); the count is only displayed inside the drawer body.
  const [stored, setStored] = React.useState<CandidateRef[]>(() => (songId ? loadExclusions(songId) : []));

  const next = React.useCallback(async () => {
    if (!songId) return;
    setLoadingCandidates(true);
    let candidates: Candidate[] | null = null;
    try {
      candidates = (await qc.fetchQuery(candidatesQuery(songId))).candidates;
    } catch {
      // Candidate listing is best-effort: the stored list + current tab still let the backend skip.
    } finally {
      setLoadingCandidates(false);
    }
    const exclude = mergeRefs(loadExclusions(songId), computeExclusions(candidates, currentTab));
    saveExclusions(songId, exclude);
    setStored(exclude);
    createJob.mutate(
      { song_id: songId, exclude, capo: 0, cost_profile: "tabgen" },
      { onSuccess: (job) => router.push(`/songs/${job.id}`) },
    );
  }, [songId, qc, currentTab, createJob, router]);

  const reset = React.useCallback(() => {
    if (!songId) return;
    clearExclusions(songId);
    setStored([]);
  }, [songId]);

  return {
    next,
    reset,
    stored,
    pending: loadingCandidates || createJob.isPending,
  };
}

export interface NextVersionButtonProps extends UseNextVersionOptions {
  size?: "xs" | "sm" | "default";
  variant?: "default" | "outline" | "secondary" | "ghost";
  className?: string;
  /** Hide the label on narrow screens (header usage). */
  compact?: boolean;
}

export function NextVersionButton({ songId, currentTab, size = "sm", variant = "outline", className, compact }: NextVersionButtonProps) {
  const { next, pending } = useNextVersion({ songId, currentTab });
  if (!songId) return null;
  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      disabled={pending}
      onClick={() => void next()}
      title="Skip this version and fetch the next one"
      data-testid="next-version"
    >
      {pending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <SkipForward data-icon="inline-start" />}
      <span className={cn(compact && "hidden sm:inline")}>Not this one, next</span>
    </Button>
  );
}

// ---------------------------------------------------------------------------
// Drawer
// ---------------------------------------------------------------------------

export interface OtherVersionsSheetProps {
  songId: string;
  currentTab?: CurrentTabRef | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Element rendered as the sheet trigger (a Button, a chip, …). Omit for a controlled sheet without trigger. */
  trigger?: React.ReactElement;
  /** Trigger contents. */
  children?: React.ReactNode;
}

export function OtherVersionsSheet({ songId, currentTab, open, onOpenChange, trigger, children }: OtherVersionsSheetProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false);
  const isOpen = open ?? uncontrolledOpen;
  const setOpen = (value: boolean) => {
    setUncontrolledOpen(value);
    onOpenChange?.(value);
  };

  return (
    <Sheet open={isOpen} onOpenChange={(value) => setOpen(value)}>
      {trigger ? <SheetTrigger render={trigger}>{children}</SheetTrigger> : null}
      <SheetContent
        side="right"
        className="data-[side=right]:sm:max-w-lg"
        aria-describedby={undefined}
        data-testid="other-versions"
      >
        <SheetHeader className="pr-12">
          <SheetTitle className="flex items-center gap-2">
            <Layers className="size-4 text-muted-foreground" /> Other versions
          </SheetTitle>
          <SheetDescription>
            Every version the fallback chain can fetch for this song, in the order it would try them.
          </SheetDescription>
        </SheetHeader>
        {isOpen ? <OtherVersionsBody songId={songId} currentTab={currentTab} /> : null}
      </SheetContent>
    </Sheet>
  );
}

export interface OtherVersionsBodyProps {
  songId: string;
  currentTab?: CurrentTabRef | null;
}

/** Drawer contents; exported for tests and for embedding outside a Sheet. */
export function OtherVersionsBody({ songId, currentTab }: OtherVersionsBodyProps) {
  const router = useRouter();
  const query = useQuery(candidatesQuery(songId));
  const createJob = useCreateJob();
  const nextVersion = useNextVersion({ songId, currentTab });
  const [fetching, setFetching] = React.useState<string | null>(null);

  const fetchCandidate = (candidate: Candidate) => {
    const key = `${candidate.source}:${candidate.external_id}`;
    setFetching(key);
    createJob.mutate(
      {
        song_id: songId,
        candidate: { source: candidate.source, external_id: candidate.external_id },
        capo: 0,
        cost_profile: "tabgen",
      },
      {
        onSuccess: (job) => router.push(`/songs/${job.id}`),
        onSettled: () => setFetching(null),
      },
    );
  };

  const groups = React.useMemo(() => groupCandidates(query.data?.candidates ?? []), [query.data]);
  const warnings = query.data?.warnings ?? [];

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4" aria-busy={query.isPending}>
        {query.isPending ? (
          <CandidateSkeletons />
        ) : query.isError ? (
          <div className="flex flex-col gap-2 rounded-lg border border-destructive/40 p-3">
            <p className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="size-4 text-destructive" /> Couldn&apos;t list versions
            </p>
            <p className="text-xs text-muted-foreground">{toApiError(query.error).detail}</p>
            <Button variant="secondary" size="sm" className="w-fit" onClick={() => void query.refetch()}>
              Retry
            </Button>
          </div>
        ) : groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No other versions were found for this song.</p>
        ) : (
          groups.map((group) => (
            <section key={group.source} className="flex flex-col gap-2" data-source-group={group.source}>
              <h3 className="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {sourceLabel(group.source)}
                <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums normal-case">
                  {group.candidates.length}
                </span>
              </h3>
              <ul className="flex flex-col gap-2" aria-label={`${sourceLabel(group.source)} versions`}>
                {group.candidates.map((c) => (
                  <CandidateRow
                    key={`${c.source}:${c.external_id}`}
                    candidate={c}
                    current={isCurrentCandidate(c, currentTab)}
                    fetching={fetching === `${c.source}:${c.external_id}`}
                    busy={createJob.isPending || nextVersion.pending}
                    onFetch={() => fetchCandidate(c)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}

        {warnings.length ? <Warnings warnings={warnings} /> : null}
      </div>

      <SheetFooter className="border-t border-border">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground" data-testid="skipped-count">
            {nextVersion.stored.length
              ? `${nextVersion.stored.length} version${nextVersion.stored.length === 1 ? "" : "s"} skipped so far`
              : "Nothing skipped yet"}
          </p>
          <div className="flex items-center gap-2">
            {nextVersion.stored.length ? (
              <Button type="button" variant="ghost" size="sm" onClick={nextVersion.reset}>
                <RotateCcw data-icon="inline-start" /> Start over
              </Button>
            ) : null}
            <Button type="button" size="sm" disabled={nextVersion.pending || createJob.isPending} onClick={() => void nextVersion.next()}>
              {nextVersion.pending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <SkipForward data-icon="inline-start" />}
              Not this one, next
            </Button>
          </div>
        </div>
      </SheetFooter>
    </>
  );
}

function CandidateSkeletons() {
  return (
    <div className="flex flex-col gap-3" data-testid="candidates-loading">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="h-1 w-full" />
        </div>
      ))}
    </div>
  );
}

interface CandidateRowProps {
  candidate: Candidate;
  current: boolean;
  fetching: boolean;
  busy: boolean;
  onFetch: () => void;
}

function CandidateRow({ candidate: c, current, fetching, busy, onFetch }: CandidateRowProps) {
  const pct = scorePercent(c.score);
  const disabled = !c.available;
  return (
    <li
      data-candidate={`${c.source}:${c.external_id}`}
      data-current={current || undefined}
      data-disabled={disabled || undefined}
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border bg-card/60 p-3",
        current && "border-primary/50 bg-primary/5",
        disabled && "opacity-70",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {c.title || "Untitled"}
            {current ? (
              <Badge variant="default" className="ml-2 align-middle">
                Current
              </Badge>
            ) : null}
          </p>
          <p className="truncate text-xs text-muted-foreground">{c.artist || "Unknown artist"}</p>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title="Match score">
          {pct}%
        </span>
      </div>

      <div className="h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {c.kind ? (
          <Badge variant="outline" className="capitalize">
            {c.kind.replaceAll("_", " ")}
          </Badge>
        ) : null}
        {typeof c.rating === "number" ? (
          <Badge variant="secondary" title="Rating">
            <Star /> {c.rating.toFixed(1)}
            {typeof c.votes === "number" ? <span className="text-muted-foreground">({c.votes})</span> : null}
          </Badge>
        ) : null}
        {typeof c.track_count === "number" ? (
          <Badge variant="outline">{c.track_count === 1 ? "1 track" : `${c.track_count} tracks`}</Badge>
        ) : null}
        {c.url ? (
          <a
            href={c.url}
            target="_blank"
            rel="noreferrer noopener"
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="size-3" /> {sourceLabel(c.source)}
          </a>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {c.tab_id ? (
          <Button
            variant={current ? "secondary" : "default"}
            size="sm"
            nativeButton={false}
            render={<Link href={`/tabs/${c.tab_id}`} />}
          >
            {current ? "Open (current)" : "Open"}
            <ArrowRight data-icon="inline-end" />
          </Button>
        ) : disabled ? (
          <Tooltip>
            <TooltipTrigger render={<span className="inline-flex" tabIndex={0} />}>
              <Button variant="outline" size="sm" disabled title={c.reason ?? undefined}>
                <Download data-icon="inline-start" /> Fetch this version
              </Button>
            </TooltipTrigger>
            {c.reason ? <TooltipContent>{c.reason}</TooltipContent> : null}
          </Tooltip>
        ) : (
          <Button variant="outline" size="sm" disabled={busy} onClick={onFetch}>
            {fetching ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Download data-icon="inline-start" />}
            Fetch this version
          </Button>
        )}
        {c.source === "audio" && disabled ? (
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/songs?tab=upload" />}>
            <Upload data-icon="inline-start" /> Upload audio
          </Button>
        ) : null}
        {disabled && c.reason ? <span className="text-xs text-muted-foreground">{c.reason}</span> : null}
      </div>
    </li>
  );
}

function Warnings({ warnings }: { warnings: string[] }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="flex flex-col gap-1 pb-2">
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="-ml-2 w-fit text-warning"
        aria-expanded={open}
        aria-controls="versions-warnings"
        onClick={() => setOpen((o) => !o)}
      >
        <AlertTriangle data-icon="inline-start" />
        {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
        <ChevronDown data-icon="inline-end" className={cn("transition-transform", open && "rotate-180")} />
      </Button>
      {open ? (
        <ul id="versions-warnings" className="list-disc pl-5 text-xs text-muted-foreground">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
