import { describe, expect, it } from "vitest";
import type { Evidence, PoolEntry } from "@/lib/api/types";
import { candidateRef, entryHref, evidenceLabel, noodleJobRequest } from "./pick";

const evidence = (partial: Partial<Evidence> = {}): Evidence => ({
  top_short: null,
  top_medium: null,
  top_long: null,
  recent: 0,
  liked: false,
  ...partial,
});

describe("evidenceLabel", () => {
  it("prefers short-term top tracks", () => {
    expect(evidenceLabel(evidence({ top_short: 0, recent: 3, liked: true }))).toBe("On repeat");
    // rank 0 is the best rank, so it must not be treated as missing
    expect(evidenceLabel(evidence({ top_short: 0 }))).toBe("On repeat");
  });

  it("falls back to recent plays, then favourites, then likes", () => {
    expect(evidenceLabel(evidence({ recent: 2, top_long: 4, liked: true }))).toBe("Recently played");
    expect(evidenceLabel(evidence({ top_medium: 10, liked: true }))).toBe("A favourite");
    expect(evidenceLabel(evidence({ top_long: 10 }))).toBe("A favourite");
    expect(evidenceLabel(evidence({ liked: true }))).toBe("Liked");
  });

  it("returns null without evidence", () => {
    expect(evidenceLabel(evidence())).toBeNull();
    expect(evidenceLabel(undefined)).toBeNull();
    expect(evidenceLabel(null)).toBeNull();
  });
});

describe("entryHref", () => {
  it("points at the tab once one exists", () => {
    expect(entryHref({ status: "ready", tab_id: "t1", job_id: "j1" })).toBe("/tabs/t1");
  });

  it("points at a running job while it is generating", () => {
    expect(entryHref({ status: "queued", tab_id: null, job_id: "j1" })).toBe("/songs/j1");
    expect(entryHref({ status: "checking", tab_id: null, job_id: "j1" })).toBe("/songs/j1");
  });

  it("has no destination for a fresh or failed entry", () => {
    expect(entryHref({ status: "new", tab_id: null, job_id: null })).toBeNull();
    expect(entryHref({ status: "failed", tab_id: null, job_id: "j1" })).toBeNull();
  });
});

describe("candidateRef", () => {
  it("narrows a stored Candidate to the ref a job request takes", () => {
    const candidate: PoolEntry["candidate"] = {
      source: "songsterr",
      external_id: "42",
      title: "Wonderwall",
      artist: "Oasis",
      score: 0.9,
      available: true,
    };
    expect(candidateRef({ candidate })).toEqual({ source: "songsterr", external_id: "42" });
    expect(candidateRef({ candidate: null })).toBeUndefined();
  });
});

describe("noodleJobRequest", () => {
  it("targets the stored candidate on the Songsterr tier only", () => {
    expect(
      noodleJobRequest({
        spotify_id: "abc123",
        candidate: {
          source: "songsterr",
          external_id: "42",
          title: "Wonderwall",
          artist: "Oasis",
          score: 0.9,
          available: true,
        },
      }),
    ).toEqual({
      song: { spotify_url: "https://open.spotify.com/track/abc123" },
      candidate: { source: "songsterr", external_id: "42" },
      tiers: ["songsterr"],
      origin: "noodle",
      capo: 0,
      cost_profile: "tabgen",
    });
  });

  it("omits the candidate when the pool has not found one", () => {
    const body = noodleJobRequest({ spotify_id: "abc123", candidate: null });
    expect(body.candidate).toBeNull();
    expect(body.song).toEqual({ spotify_url: "https://open.spotify.com/track/abc123" });
  });
});
