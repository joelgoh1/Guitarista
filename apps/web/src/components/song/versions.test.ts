import { afterEach, describe, expect, it } from "vitest";
import type { Candidate } from "@/lib/api/types";
import {
  candidateRefFromTab,
  clearExclusions,
  computeExclusions,
  groupCandidates,
  isCurrentCandidate,
  loadExclusions,
  mergeRefs,
  saveExclusions,
  scorePercent,
} from "@/components/song/versions";

function candidate(partial: Partial<Candidate> & Pick<Candidate, "source" | "external_id">): Candidate {
  return {
    title: "Wonderwall",
    artist: "Oasis",
    score: 0.5,
    kind: null,
    rating: null,
    votes: null,
    track_count: null,
    url: null,
    tab_id: null,
    available: true,
    reason: null,
    ...partial,
  };
}

const candidates: Candidate[] = [
  candidate({ source: "songsterr", external_id: "1", tab_id: "tab1", score: 0.98 }),
  candidate({ source: "songsterr", external_id: "2", score: 0.7 }),
  candidate({ source: "ultimate_guitar", external_id: "777", tab_id: "tab7", score: 0.6 }),
  candidate({ source: "ultimate_guitar", external_id: "778", score: 0.4 }),
  candidate({ source: "audio", external_id: "audio", available: false, reason: "Upload audio first", score: 0 }),
];

describe("candidateRefFromTab", () => {
  it("parses songsterr and ug source refs", () => {
    expect(candidateRefFromTab({ id: "t", source: "songsterr", source_ref: "songsterr:123:456:[0, 1]" })).toEqual({
      source: "songsterr",
      external_id: "123",
    });
    expect(candidateRefFromTab({ id: "t", source: "ultimate_guitar", source_ref: "ug:777" })).toEqual({
      source: "ultimate_guitar",
      external_id: "777",
    });
  });

  it("maps audio tabs onto the audio candidate and ignores manual tabs", () => {
    expect(candidateRefFromTab({ id: "t", source: "audio", source_ref: null })?.source).toBe("audio");
    expect(candidateRefFromTab({ id: "t", source: "manual", source_ref: null })).toBeNull();
    expect(candidateRefFromTab(null)).toBeNull();
  });
});

describe("isCurrentCandidate", () => {
  it("matches by tab_id or by source_ref external id", () => {
    const tab = { id: "tab1", source: "songsterr" as const, source_ref: "songsterr:1:2:[0]" };
    expect(isCurrentCandidate(candidates[0]!, tab)).toBe(true);
    expect(isCurrentCandidate(candidates[1]!, tab)).toBe(false);
    const byRef = { id: "other", source: "songsterr" as const, source_ref: "songsterr:2:9" };
    expect(isCurrentCandidate(candidates[1]!, byRef)).toBe(true);
    expect(isCurrentCandidate(candidates[2]!, byRef)).toBe(false);
  });
});

describe("computeExclusions", () => {
  it("includes every fetched candidate plus the current tab's own candidate", () => {
    const current = { id: "tabX", source: "songsterr" as const, source_ref: "songsterr:2:5:[0]" };
    expect(computeExclusions(candidates, current)).toEqual([
      { source: "songsterr", external_id: "1" },
      { source: "songsterr", external_id: "2" },
      { source: "ultimate_guitar", external_id: "777" },
    ]);
  });

  it("falls back to the current tab when candidates failed to load", () => {
    const current = { id: "tab7", source: "ultimate_guitar" as const, source_ref: "ug:777" };
    expect(computeExclusions(null, current)).toEqual([{ source: "ultimate_guitar", external_id: "777" }]);
    expect(computeExclusions([], null)).toEqual([]);
  });

  it("dedupes with mergeRefs", () => {
    expect(
      mergeRefs(
        [{ source: "songsterr", external_id: "1" }],
        [{ source: "songsterr", external_id: "1" }, { source: "audio", external_id: "audio" }],
      ),
    ).toHaveLength(2);
  });
});

describe("groupCandidates / scorePercent", () => {
  it("groups in Songsterr → UG → audio order", () => {
    const groups = groupCandidates([...candidates].reverse());
    expect(groups.map((g) => g.source)).toEqual(["songsterr", "ultimate_guitar", "audio"]);
    expect(groups[0]!.candidates.map((c) => c.external_id)).toEqual(["2", "1"]);
  });

  it("clamps scores", () => {
    expect(scorePercent(0.98)).toBe(98);
    expect(scorePercent(75)).toBe(75);
    expect(scorePercent(150)).toBe(100);
    expect(scorePercent(null)).toBe(0);
  });
});

describe("sessionStorage exclusions", () => {
  afterEach(() => clearExclusions("song1"));

  it("round-trips and ignores garbage", () => {
    saveExclusions("song1", [{ source: "songsterr", external_id: "1" }]);
    expect(loadExclusions("song1")).toEqual([{ source: "songsterr", external_id: "1" }]);
    window.sessionStorage.setItem("guitarista:exclusions:song1", "{not json");
    expect(loadExclusions("song1")).toEqual([]);
    window.sessionStorage.setItem("guitarista:exclusions:song1", JSON.stringify([{ source: "bogus", external_id: "x" }, 1]));
    expect(loadExclusions("song1")).toEqual([]);
    clearExclusions("song1");
    expect(window.sessionStorage.getItem("guitarista:exclusions:song1")).toBeNull();
  });
});
