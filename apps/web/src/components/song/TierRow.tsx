"use client";

import * as React from "react";
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock,
  Loader2,
  MinusCircle,
  Sparkles,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SongsterrCandidate, TierStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/components/library/format";
import { tierDurationMs, type TierView } from "./tiers";

export const STATUS_META: Record<TierStatus, { label: string; icon: React.ComponentType<{ className?: string }>; className: string }> = {
  pending: { label: "Pending", icon: Circle, className: "text-muted-foreground/60" },
  running: { label: "Running", icon: Loader2, className: "text-primary animate-spin" },
  success: { label: "Success", icon: CheckCircle2, className: "text-success" },
  skipped: { label: "Skipped", icon: MinusCircle, className: "text-muted-foreground" },
  failed: { label: "Failed", icon: XCircle, className: "text-destructive" },
  timeout: { label: "Timed out", icon: Clock, className: "text-warning" },
  cancelled: { label: "Cancelled", icon: Ban, className: "text-muted-foreground" },
};

export interface TierRowProps {
  tier: TierView;
  now: number;
  isLast?: boolean;
}

export function TierRow({ tier, now, isLast }: TierRowProps) {
  const meta = STATUS_META[tier.status];
  const Icon = meta.icon;
  const duration = tierDurationMs(tier, now);
  const detail = tier.detail ?? {};
  const hasDetail = Object.keys(detail).length > 0;
  const [open, setOpen] = React.useState(false);
  const panelId = `tier-${tier.tier}-detail`;

  return (
    <li
      data-tier={tier.tier}
      data-status={tier.status}
      className={cn("relative flex gap-3 pb-6", isLast && "pb-0")}
    >
      {!isLast ? (
        <span aria-hidden className="absolute top-6 left-[11px] h-[calc(100%-1.5rem)] w-px bg-border" />
      ) : null}
      <motion.span
        key={tier.status}
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 400, damping: 22 }}
        className="relative z-[1] mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-background"
      >
        <Icon className={cn("size-5", meta.className)} />
        <span className="sr-only">{meta.label}</span>
      </motion.span>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={cn("text-sm font-medium", tier.status === "pending" && "text-muted-foreground")}>
            {tier.label}
          </span>
          <Badge variant={badgeVariant(tier.status)} className="capitalize">
            {meta.label}
          </Badge>
          {detail.llm_used === true ? (
            <Badge variant="outline" className="gap-1">
              <Sparkles /> LLM ranked
            </Badge>
          ) : null}
          {duration !== null && tier.status !== "pending" ? (
            <span className="text-xs text-muted-foreground tabular-nums">{formatDuration(duration)}</span>
          ) : null}
        </div>
        <p className={cn("text-sm", tier.message ? "text-foreground/80" : "text-muted-foreground")}>
          {tier.message ?? tier.description}
        </p>
        {hasDetail ? (
          <div className="mt-1">
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className="-ml-2 text-muted-foreground"
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => setOpen((o) => !o)}
            >
              Details
              <ChevronDown data-icon="inline-end" className={cn("transition-transform", open && "rotate-180")} />
            </Button>
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  id={panelId}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="overflow-hidden"
                >
                  <TierDetail detail={detail} />
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        ) : null}
      </div>
    </li>
  );
}

function badgeVariant(status: TierStatus): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "success":
      return "default";
    case "failed":
    case "timeout":
      return "destructive";
    case "running":
      return "secondary";
    default:
      return "outline";
  }
}

function isCandidateList(value: unknown): value is SongsterrCandidate[] {
  return Array.isArray(value) && value.every((c) => c && typeof c === "object");
}

/** The audio tier's `input`: which file or video the transcription actually came from. */
interface AudioInput {
  kind?: string;
  url?: string;
  title?: string;
  uploader?: string;
  duration_s?: number;
  expected_duration_s?: number | null;
  considered?: { video_id?: string; title?: string; score?: number; rejected?: string }[];
}

function secs(value: unknown): string {
  return typeof value === "number" ? formatDuration(value * 1000) : "—";
}

function AudioInputDetail({ input }: { input: AudioInput }) {
  const considered = Array.isArray(input.considered) ? input.considered : [];
  return (
    <div className="flex flex-col gap-1">
      <p>
        <span className="text-muted-foreground">
          {input.kind === "ytdlp_url" ? "Audio from URL: " : "Matched video: "}
        </span>
        {input.url ? (
          <a href={input.url} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2">
            {input.title || input.url}
          </a>
        ) : (
          (input.title ?? "—")
        )}
        {input.uploader ? <span className="text-muted-foreground"> · {input.uploader}</span> : null}
      </p>
      {input.kind === "ytdlp" ? (
        <p className="text-muted-foreground">
          Duration {secs(input.duration_s)} vs expected {secs(input.expected_duration_s)}
          {considered.length > 1 ? ` · ${considered.length} results considered` : null}
        </p>
      ) : null}
      {considered.length > 1 ? (
        <ul className="mt-0.5 flex flex-col gap-0.5 text-muted-foreground">
          {considered.slice(1).map((c, i) => (
            <li key={c.video_id ?? i} className="truncate">
              {typeof c.score === "number" ? c.score.toFixed(2) : "—"} · {c.title ?? "—"}
              {c.rejected ? ` — ${c.rejected}` : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function TierDetail({ detail }: { detail: Record<string, unknown> }) {
  const { candidates, picked, llm_used: _llm, tracks, input, ...rest } = detail;
  void _llm;
  const candidate = input && typeof input === "object" ? (input as AudioInput) : null;
  const audioInput = candidate?.kind === "ytdlp" || candidate?.kind === "ytdlp_url" ? candidate : null;
  // Anything this component does not render specially still belongs in the raw dump below.
  if (input !== undefined && audioInput === null) rest.input = input;
  const pickedId = picked && typeof picked === "object" ? String((picked as SongsterrCandidate).songId ?? "") : "";

  return (
    <div className="mt-2 flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-3 text-xs">
      {audioInput ? <AudioInputDetail input={audioInput} /> : null}
      {isCandidateList(candidates) && candidates.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <caption className="sr-only">Candidates</caption>
            <thead className="text-muted-foreground">
              <tr>
                <th className="pr-3 pb-1 font-medium">Title</th>
                <th className="pr-3 pb-1 font-medium">Artist</th>
                <th className="pb-1 text-right font-medium">Score</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => {
                const isPicked = pickedId !== "" && String(c.songId ?? "") === pickedId;
                return (
                  <tr key={`${c.songId ?? i}`} className={cn(isPicked && "text-primary")}>
                    <td className="pr-3 py-0.5">
                      {c.title ?? "—"}
                      {isPicked ? <span className="ml-1 text-[10px] uppercase">picked</span> : null}
                    </td>
                    <td className="pr-3 py-0.5">{c.artist ?? "—"}</td>
                    <td className="py-0.5 text-right tabular-nums">
                      {typeof c.score === "number" ? c.score.toFixed(2) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {Array.isArray(tracks) && tracks.length ? (
        <p>
          <span className="text-muted-foreground">Tracks: </span>
          {tracks.map((t) => (typeof t === "string" ? t : JSON.stringify(t))).join(", ")}
        </p>
      ) : null}
      {picked && !isCandidateList(candidates) ? (
        <p>
          <span className="text-muted-foreground">Picked: </span>
          {JSON.stringify(picked)}
        </p>
      ) : null}
      {Object.keys(rest).length ? (
        <pre className="overflow-x-auto font-mono text-[11px] text-muted-foreground">
          {JSON.stringify(rest, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
