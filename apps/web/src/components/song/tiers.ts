import type { Job, TierLogEntry, TierName, TierStatus } from "@/lib/api/types";

/** Fallback order when /health has not answered yet. */
export const DEFAULT_TIER_ORDER: TierName[] = ["resolve", "songsterr", "ultimate_guitar", "audio"];

export const TIER_LABELS: Record<TierName, string> = {
  resolve: "Resolve song",
  songsterr: "Songsterr",
  ultimate_guitar: "Ultimate Guitar",
  audio: "Audio transcription",
};

export const TIER_DESCRIPTIONS: Record<TierName, string> = {
  resolve: "Identify artist and title (Spotify or text).",
  songsterr: "Look up an existing tab on Songsterr.",
  ultimate_guitar: "Parse a tab from Ultimate Guitar.",
  audio: "Transcribe from audio with basic-pitch and solve frettings.",
};

export interface TierView extends TierLogEntry {
  label: string;
  description: string;
  /** Row was synthesised (no backend log entry yet). */
  synthetic: boolean;
}

function isTierName(value: string): value is TierName {
  return value in TIER_LABELS;
}

/**
 * Merge `/health.tiers` (source order) with the job's tier log. Unknown tiers
 * from the backend are appended so nothing is hidden.
 */
export function mergeTiers(healthTiers: string[] | undefined, job: Job | undefined): TierView[] {
  const order: TierName[] = ["resolve"];
  for (const t of healthTiers?.length ? healthTiers : DEFAULT_TIER_ORDER) {
    if (isTierName(t) && !order.includes(t)) order.push(t);
  }
  const requested = job?.request?.tiers ?? null;
  const logged = new Map<string, TierLogEntry>();
  for (const entry of job?.tiers ?? []) {
    logged.set(entry.tier, entry);
    if (isTierName(entry.tier) && !order.includes(entry.tier)) order.push(entry.tier);
  }

  return order.map((tier) => {
    const entry = logged.get(tier);
    if (entry) {
      return { ...entry, label: TIER_LABELS[tier], description: TIER_DESCRIPTIONS[tier], synthetic: false };
    }
    const status: TierStatus =
      tier === "resolve"
        ? resolveStatus(job)
        : requested && !requested.includes(tier as Exclude<TierName, "resolve">)
          ? "skipped"
          : pendingStatus(job);
    return {
      tier,
      status,
      message: tier === "resolve" ? resolveMessage(job, status) : null,
      detail: {},
      label: TIER_LABELS[tier],
      description: TIER_DESCRIPTIONS[tier],
      synthetic: true,
    };
  });
}

/** The resolver isn't a logged tier (yet); derive its state from the job. */
function resolveStatus(job: Job | undefined): TierStatus {
  if (!job) return "pending";
  if (job.song_id) return "success";
  switch (job.status) {
    case "queued":
      return "pending";
    case "running":
      return "running";
    case "cancelled":
      return "cancelled";
    case "failed":
    case "interrupted":
      return "failed";
    case "done":
      return "success";
  }
}

function resolveMessage(job: Job | undefined, status: TierStatus): string | null {
  if (!job) return null;
  if (status === "failed") return job.error ?? null;
  return null;
}

/** Tiers without a log entry: cancelled/failed jobs never reached them. */
function pendingStatus(job: Job | undefined): TierStatus {
  if (!job) return "pending";
  if (job.status === "cancelled") return "cancelled";
  if (job.status === "failed" || job.status === "interrupted" || job.status === "done") return "skipped";
  return "pending";
}

export function tierDurationMs(entry: Pick<TierLogEntry, "started_at" | "finished_at">, now: number): number | null {
  if (!entry.started_at) return null;
  const start = Date.parse(entry.started_at);
  if (Number.isNaN(start)) return null;
  const end = entry.finished_at ? Date.parse(entry.finished_at) : now;
  return Math.max(0, end - start);
}
