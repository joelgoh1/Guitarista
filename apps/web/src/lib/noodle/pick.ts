import type { CreateJobRequest, Evidence, PoolEntry } from "@/lib/api/types";

/**
 * Why a song is in the pool, in one chip. Precedence is strongest signal first:
 * short-term top tracks beat a recent play, which beats a long-standing
 * favourite, which beats a plain like.
 */
export function evidenceLabel(evidence: Evidence | null | undefined): string | null {
  if (!evidence) return null;
  if (evidence.top_short != null) return "On repeat";
  if (evidence.recent > 0) return "Recently played";
  if (evidence.top_medium != null || evidence.top_long != null) return "A favourite";
  if (evidence.liked) return "Liked";
  return null;
}

/**
 * Where a pool card points: a ready entry opens its tab, anything else stays on
 * the page (the card renders a Generate button instead).
 */
export function entryHref(entry: Pick<PoolEntry, "status" | "tab_id" | "job_id">): string | null {
  if (entry.tab_id) return `/tabs/${entry.tab_id}`;
  if (entry.job_id && (entry.status === "queued" || entry.status === "checking")) {
    return `/songs/${entry.job_id}`;
  }
  return null;
}

/** `PoolEntry.candidate` is a full Candidate; `TabRequest.candidate` wants the ref. */
export function candidateRef(entry: Pick<PoolEntry, "candidate">) {
  const candidate = entry.candidate;
  if (!candidate) return undefined;
  return { source: candidate.source, external_id: candidate.external_id };
}

export function spotifyTrackUrlFor(spotifyId: string): string {
  return `https://open.spotify.com/track/${spotifyId}`;
}

/**
 * The `POST /jobs` body for one pool entry: Songsterr only (noodle jobs stay
 * cheap) and tagged `origin: "noodle"` so the backend can tell them apart.
 */
export function noodleJobRequest(
  entry: Pick<PoolEntry, "spotify_id" | "candidate">,
): CreateJobRequest {
  return {
    song: { spotify_url: spotifyTrackUrlFor(entry.spotify_id) },
    candidate: candidateRef(entry) ?? null,
    tiers: ["songsterr"],
    origin: "noodle",
    capo: 0,
    cost_profile: "tabgen",
  };
}
