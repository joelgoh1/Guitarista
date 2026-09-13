import { describe, expect, it } from "vitest";
import type { AlphaTabModule } from "@/lib/alphatab/loader";
import { toAlphaTabRhythmMode } from "@/lib/alphatab/settings";

const TabRhythmMode = { Hidden: 0, ShowWithBeams: 1, ShowWithBars: 2 } as const;

function fakeModule(): AlphaTabModule {
  return { TabRhythmMode } as unknown as AlphaTabModule;
}

describe("toAlphaTabRhythmMode", () => {
  it("hides the tab rhythm when the standard staff carries it", () => {
    expect(toAlphaTabRhythmMode(fakeModule(), "scoreTab")).toBe(TabRhythmMode.Hidden);
  });

  it("shows grouped (bar) rhythm on a tab-only stave", () => {
    expect(toAlphaTabRhythmMode(fakeModule(), "tab")).toBe(TabRhythmMode.ShowWithBars);
  });
});
