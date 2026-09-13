"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Ban, CheckCircle2, Layers, Loader2, Upload } from "lucide-react";
import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { healthQuery, jobQuery, tabQuery, useCancelJob } from "@/lib/api/queries";
import { isTerminalJob, type Job, type JobStatus } from "@/lib/api/types";
import { toApiError } from "@/lib/api/problem";
import { useJobEvents } from "@/hooks/useJobEvents";
import { useNow } from "@/hooks/useNow";
import { formatDuration } from "@/components/library/format";
import { mergeTiers } from "./tiers";
import { TierRow } from "./TierRow";
import { NextVersionButton, OtherVersionsSheet } from "./OtherVersions";

export const REDIRECT_DELAY_MS = 1200;

const STATUS_BADGE: Record<JobStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  queued: { label: "Queued", variant: "outline" },
  running: { label: "Running", variant: "secondary" },
  done: { label: "Done", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "outline" },
  interrupted: { label: "Interrupted", variant: "destructive" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const meta = STATUS_BADGE[status];
  return (
    <Badge variant={meta.variant} data-status={status}>
      {status === "running" ? <Loader2 className="animate-spin" /> : null}
      {meta.label}
    </Badge>
  );
}

export interface JobProgressProps {
  jobId: string;
  /** Disable the SSE stream (tests). */
  live?: boolean;
  /** Disable the auto-redirect (tests). */
  autoRedirect?: boolean;
}

export function JobProgress({ jobId, live = true, autoRedirect = true }: JobProgressProps) {
  const router = useRouter();
  const events = useJobEvents(jobId, { enabled: live });
  const job = useQuery(jobQuery(jobId, { sseConnected: events.connected }));
  const health = useQuery(healthQuery());
  const cancel = useCancelJob();
  const data = job.data;
  const terminal = isTerminalJob(data);
  const now = useNow(terminal ? null : 1000);

  const tiers = React.useMemo(() => mergeTiers(health.data?.tiers, data), [health.data?.tiers, data]);

  // Auto-redirect to the tab once done.
  React.useEffect(() => {
    if (!autoRedirect || data?.status !== "done" || !data.tab_id) return;
    const tabId = data.tab_id;
    const t = setTimeout(() => router.replace(`/tabs/${tabId}`), REDIRECT_DELAY_MS);
    return () => clearTimeout(t);
  }, [autoRedirect, data?.status, data?.tab_id, router]);

  if (job.isPending) {
    return (
      <Card className="max-w-2xl">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  // A failed background refetch keeps the cached snapshot; only bail when there is none.
  if (!data) {
    const err = toApiError(job.error);
    return (
      <Card className="max-w-2xl border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-destructive" /> {err.title}
          </CardTitle>
          <CardDescription>{err.detail}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="secondary" nativeButton={false} render={<Link href="/songs" />}>
            Back to Song → Tab
          </Button>
        </CardContent>
      </Card>
    );
  }

  const elapsed = elapsedMs(data, now);
  const progressPct = Math.round(Math.min(1, Math.max(0, data.progress ?? 0)) * 100);
  const lastMessage = [...(data.tiers ?? [])].reverse().find((t) => t.message)?.message ?? null;

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Tier timeline</CardTitle>
            <div className="flex items-center gap-2">
              {events.connected ? (
                <span className="text-xs text-muted-foreground" title="Server-sent events connected">
                  live
                </span>
              ) : events.fallback && !terminal ? (
                <span className="text-xs text-muted-foreground" title="SSE unavailable, polling">
                  polling
                </span>
              ) : null}
              <JobStatusBadge status={data.status} />
            </div>
          </div>
          <CardDescription>{describeRequest(data)}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <Progress value={progressPct} aria-label="Job progress">
            <ProgressLabel className="text-muted-foreground">
              {terminal ? `Finished in ${formatDuration(elapsed)}` : `Elapsed ${formatDuration(elapsed)}`}
              {lastMessage && !terminal ? ` · ${lastMessage}` : ""}
            </ProgressLabel>
            <ProgressValue />
          </Progress>

          <ol className="flex flex-col" aria-label="Tiers">
            {tiers.map((tier, i) => (
              <TierRow key={tier.tier} tier={tier} now={now} isLast={i === tiers.length - 1} />
            ))}
          </ol>

          {!terminal ? (
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(jobId)}
              >
                {cancel.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Ban data-icon="inline-start" />}
                Cancel
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {data.status === "done" && data.tab_id ? (
        <DoneCard tabId={data.tab_id} songId={data.song_id ?? null} autoRedirect={autoRedirect} />
      ) : null}
      {(data.status === "failed" || data.status === "interrupted") ? <FailedCard job={data} /> : null}
      {data.status === "cancelled" ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Ban className="size-4 text-muted-foreground" /> Cancelled
            </CardTitle>
            <CardDescription>This job was cancelled before a tab was produced.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="secondary" nativeButton={false} render={<Link href="/songs" />}>
              Start over
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function DoneCard({ tabId, songId, autoRedirect }: { tabId: string; songId: string | null; autoRedirect: boolean }) {
  const tab = useQuery(tabQuery(tabId));
  const currentTab = tab.data ?? { id: tabId, source: "manual" as const, source_ref: null };
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Card className="border-success/40" data-testid="job-done">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="size-4 text-success" />
            {tab.data ? tab.data.title : "Tab ready"}
          </CardTitle>
          <CardDescription>
            {tab.data?.artist ? `${tab.data.artist} · ` : ""}
            {autoRedirect ? "Opening your tab…" : "Your tab is ready."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button nativeButton={false} render={<Link href={`/tabs/${tabId}`} />}>
            Open tab
            <ArrowRight data-icon="inline-end" />
          </Button>
          {songId ? (
            <>
              <NextVersionButton songId={songId} currentTab={currentTab} size="default" />
              <OtherVersionsSheet songId={songId} currentTab={currentTab} trigger={<Button variant="ghost" />}>
                <Layers data-icon="inline-start" /> Other versions
              </OtherVersionsSheet>
            </>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function FailedCard({ job }: { job: Job }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Card className="border-destructive/40" data-testid="job-failed">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-destructive" /> No tab found
          </CardTitle>
          <CardDescription>{job.error ?? "Every tier failed or was skipped."}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button nativeButton={false} render={<Link href="/songs?tab=upload" />}>
            <Upload data-icon="inline-start" />
            Upload audio or paste a URL
          </Button>
          <Button variant="outline" nativeButton={false} render={<Link href="/songs" />}>
            Try another song
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function elapsedMs(job: Job, now: number): number {
  const start = job.created_at ? Date.parse(job.created_at) : NaN;
  if (Number.isNaN(start)) return 0;
  const end = isTerminalJob(job) && job.updated_at ? Date.parse(job.updated_at) : now;
  return Math.max(0, (Number.isNaN(end) ? now : end) - start);
}

function describeRequest(job: Job): string {
  const song = job.request?.song;
  if (song?.title || song?.artist) return [song.artist, song.title].filter(Boolean).join(" — ");
  if (song?.raw) return `“${song.raw}”`;
  if (song?.spotify_url) return song.spotify_url;
  if (job.request?.upload_id) return `Uploaded audio ${job.request.upload_id.slice(0, 8)}…`;
  return "Songsterr → Ultimate Guitar → Audio transcription";
}
