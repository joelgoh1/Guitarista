import type { components } from "@guitarista/api-types";

type Schemas = components["schemas"];

export type Health = Schemas["Health"];
export type Features = Schemas["Features"];
export type Song = Schemas["Song"];
export type SongQuery = Schemas["SongQuery"];
export type TabRequest = Schemas["TabRequest"];
export type Tab = Schemas["Tab"];
export type Track = Schemas["Track"];
export type TabSummary = Schemas["TabSummary"];
export type TabSourceKind = Schemas["TabSourceKind"];
export type ScorePart = Schemas["ScorePart"];
export type ScoreUploadResponse = Schemas["ScoreUploadResponse"];
export type ScoreTabRequest = Schemas["ScoreTabRequest"];
export type OutOfRangePolicy = ScoreTabRequest["out_of_range"];
/** Solver fretting preference; shared by song → tab (audio tier) and score → tab. */
export type CostProfile = TabRequest["cost_profile"];

export type JobStatus = Schemas["Job"]["status"];
export type TierStatus = Schemas["TierLogEntry"]["status"];

/**
 * The backend currently types tiers as songsterr | ultimate_guitar | audio; the
 * song-resolution step is planned to surface as a `resolve` tier as well, so the
 * UI accepts the wider union.
 */
export type TierName = Schemas["TierLogEntry"]["tier"] | "resolve";

export interface TierLogEntry extends Omit<Schemas["TierLogEntry"], "tier"> {
  tier: TierName;
}

export interface Job extends Omit<Schemas["Job"], "tiers" | "id"> {
  id: string;
  tiers?: TierLogEntry[];
}

export type AudioUploadResponse = Schemas["AudioUploadResponse"];

// ---------------------------------------------------------------------------
// Noodle mode (Spotify listening pool)
// ---------------------------------------------------------------------------

export type SpotifyStatus = Schemas["SpotifyStatus"];
export type PoolEntry = Schemas["PoolEntry"];
export type PoolSummary = Schemas["PoolSummary"];
export type SurprisePick = Schemas["SurprisePick"];
export type Evidence = Schemas["Evidence"];
export type PoolEntryStatus = PoolEntry["status"];

export const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set([
  "done",
  "failed",
  "cancelled",
  "interrupted",
]);

export function isTerminalJob(job: Pick<Job, "status"> | undefined | null): boolean {
  return !!job && TERMINAL_JOB_STATUSES.has(job.status);
}

/** Songsterr candidate rows as written by the backend's songsterr source. */
export interface SongsterrCandidate {
  songId?: string | number;
  title?: string;
  artist?: string;
  score?: number;
}

// ---------------------------------------------------------------------------
// Other versions / candidates (`POST /songs/{song_id}/candidates`)
// ---------------------------------------------------------------------------

export type Candidate = Schemas["Candidate"];
export type CandidateRef = Schemas["CandidateRef"];
export type CandidateSource = CandidateRef["source"];
export type CandidatesRequest = Schemas["CandidatesRequest"];
export type CandidatesResponse = Schemas["CandidatesResponse"];

/** Fallback-chain order; also the grouping order in the "Other versions" drawer. */
export const CANDIDATE_SOURCE_ORDER: readonly CandidateSource[] = ["songsterr", "ultimate_guitar", "audio"];

/**
 * `POST /jobs` body. The generated `TabRequest` already carries `song_id`,
 * `candidate` and `exclude`; this alias names the intent at call sites.
 * `origin` has a server-side default ("user"), so callers may leave it out.
 */
export type CreateJobRequest = Omit<TabRequest, "origin"> & { origin?: TabRequest["origin"] };
