import {
  CANDIDATE_SOURCE_ORDER,
  type Candidate,
  type CandidateRef,
  type CandidateSource,
  type Tab,
} from "@/lib/api/types";

/** The subset of a tab needed to recognise which candidate it came from. */
export type CurrentTabRef = Pick<Tab, "id" | "source" | "source_ref">;

export interface CandidateGroup {
  source: CandidateSource;
  candidates: Candidate[];
}

function isCandidateSource(value: string): value is CandidateSource {
  return (CANDIDATE_SOURCE_ORDER as readonly string[]).includes(value);
}

/**
 * Parse a tab's `source_ref` into the candidate it was fetched from:
 * `songsterr:{songId}:{revision}:[...]` → `{songsterr, songId}`, `ug:{id}` → `{ultimate_guitar, id}`.
 * Audio tabs have no external id; they map onto the single audio candidate.
 */
export function candidateRefFromTab(tab: CurrentTabRef | null | undefined): CandidateRef | null {
  if (!tab) return null;
  const ref = tab.source_ref ?? "";
  const songsterr = /^songsterr:([^:]+)/.exec(ref);
  if (songsterr) return { source: "songsterr", external_id: songsterr[1]! };
  const ug = /^(?:ug|ultimate_guitar):([^:]+)/.exec(ref);
  if (ug) return { source: "ultimate_guitar", external_id: ug[1]! };
  if (tab.source === "audio") return { source: "audio", external_id: ref || "audio" };
  return null;
}

/** True when `candidate` produced the currently open tab. */
export function isCurrentCandidate(candidate: Candidate, tab: CurrentTabRef | null | undefined): boolean {
  if (!tab) return false;
  if (candidate.tab_id && candidate.tab_id === tab.id) return true;
  const ref = candidateRefFromTab(tab);
  if (!ref || ref.source !== candidate.source) return false;
  // There is exactly one audio "candidate" per song; any audio tab came from it.
  if (candidate.source === "audio") return true;
  return ref.external_id === candidate.external_id;
}

export function sameRef(a: CandidateRef, b: CandidateRef): boolean {
  return a.source === b.source && a.external_id === b.external_id;
}

export function mergeRefs(...lists: Array<readonly CandidateRef[] | null | undefined>): CandidateRef[] {
  const out: CandidateRef[] = [];
  for (const list of lists) {
    for (const ref of list ?? []) {
      if (isCandidateSource(ref.source) && ref.external_id && !out.some((r) => sameRef(r, ref))) {
        out.push({ source: ref.source, external_id: ref.external_id });
      }
    }
  }
  return out;
}

/**
 * Everything already tried for this song: every candidate that has a stored tab,
 * plus the candidate the current tab came from (even when the candidate list
 * doesn't know about it yet, or failed to load).
 */
export function computeExclusions(
  candidates: readonly Candidate[] | null | undefined,
  currentTab: CurrentTabRef | null | undefined,
): CandidateRef[] {
  const tried: CandidateRef[] = [];
  for (const c of candidates ?? []) {
    if (c.tab_id || isCurrentCandidate(c, currentTab)) tried.push(c);
  }
  const own = candidateRefFromTab(currentTab);
  return mergeRefs(tried, own ? [own] : null);
}

/** Group in the fallback-chain order; unknown sources are appended. */
export function groupCandidates(candidates: readonly Candidate[]): CandidateGroup[] {
  const groups = new Map<CandidateSource, Candidate[]>();
  for (const source of CANDIDATE_SOURCE_ORDER) groups.set(source, []);
  for (const c of candidates) {
    const list = groups.get(c.source);
    if (list) list.push(c);
    else groups.set(c.source, [c]);
  }
  return [...groups.entries()].filter(([, list]) => list.length).map(([source, list]) => ({ source, candidates: list }));
}

/** Score is 0..1 from the ranker; be lenient with 0..100 just in case. */
export function scorePercent(score: number | null | undefined): number {
  if (typeof score !== "number" || Number.isNaN(score)) return 0;
  const pct = score <= 1 ? score * 100 : score;
  return Math.round(Math.min(100, Math.max(0, pct)));
}

// ---------------------------------------------------------------------------
// Per-song exclusion memory (sessionStorage) so repeated "next" keeps walking.
// ---------------------------------------------------------------------------

const STORAGE_PREFIX = "guitarista:exclusions:";

function storageKey(songId: string): string {
  return `${STORAGE_PREFIX}${songId}`;
}

function getStorage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export function loadExclusions(songId: string): CandidateRef[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(storageKey(songId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return mergeRefs(
      parsed.filter(
        (r): r is CandidateRef =>
          !!r && typeof r === "object" && typeof (r as CandidateRef).source === "string" && typeof (r as CandidateRef).external_id === "string",
      ),
    );
  } catch {
    return [];
  }
}

export function saveExclusions(songId: string, refs: readonly CandidateRef[]): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    if (refs.length) storage.setItem(storageKey(songId), JSON.stringify(refs));
    else storage.removeItem(storageKey(songId));
  } catch {
    // quota / privacy mode: the in-memory list still works for this click
  }
}

export function clearExclusions(songId: string): void {
  saveExclusions(songId, []);
}
