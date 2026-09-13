import { describe, expect, it, vi } from "vitest";
import type * as alphaTab from "@coderline/alphatab";
import { applyCapoPlayback } from "@/lib/alphatab/controls";

function fakeApi(capos: number[]) {
  const tracks = capos.map((capo, index) => ({ index, staves: [{ capo }] }));
  const changeTrackTranspositionPitch = vi.fn();
  const api = { score: { tracks }, changeTrackTranspositionPitch };
  return { api: api as unknown as alphaTab.AlphaTabApi, tracks, changeTrackTranspositionPitch };
}

describe("applyCapoPlayback", () => {
  it("transposes a capo track down by the capo fret when the capo is off", () => {
    const { api, tracks, changeTrackTranspositionPitch } = fakeApi([2]);
    applyCapoPlayback(api, false);
    expect(changeTrackTranspositionPitch).toHaveBeenCalledTimes(1);
    expect(changeTrackTranspositionPitch).toHaveBeenCalledWith([tracks[0]], -2);
  });

  it("clears the transposition when the capo is on", () => {
    const { api, tracks, changeTrackTranspositionPitch } = fakeApi([2]);
    applyCapoPlayback(api, true);
    expect(changeTrackTranspositionPitch).toHaveBeenCalledWith([tracks[0]], 0);
  });

  it("ignores tracks without a capo", () => {
    const { api, tracks, changeTrackTranspositionPitch } = fakeApi([0, 3]);
    applyCapoPlayback(api, false);
    expect(changeTrackTranspositionPitch).toHaveBeenCalledTimes(1);
    expect(changeTrackTranspositionPitch).toHaveBeenCalledWith([tracks[1]], -3);
  });

  it("does nothing without a loaded score", () => {
    const changeTrackTranspositionPitch = vi.fn();
    const api = { score: null, changeTrackTranspositionPitch } as unknown as alphaTab.AlphaTabApi;
    applyCapoPlayback(api, false);
    expect(changeTrackTranspositionPitch).not.toHaveBeenCalled();
  });
});
