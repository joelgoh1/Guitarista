import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type * as alphaTab from "@coderline/alphatab";
import { TabTransport } from "@/components/tab/TabTransport";
import { usePlayerStore, type TrackInfo } from "@/lib/stores/player";

const changeTrackTranspositionPitch = vi.fn();
const api = {
  score: { tracks: [{ index: 0, staves: [{ capo: 2 }] }] },
  changeTrackTranspositionPitch,
} as unknown as alphaTab.AlphaTabApi;

vi.mock("@/lib/alphatab/context", () => ({
  usePlayerApi: () => api,
}));

function track(capo: number): TrackInfo {
  return { index: 0, name: "Guitar", isMute: false, isSolo: false, visible: true, capo };
}

afterEach(() => {
  usePlayerStore.getState().reset();
  changeTrackTranspositionPitch.mockClear();
});

describe("TabTransport capo toggle", () => {
  it("is hidden when no track has a capo", () => {
    usePlayerStore.setState({ tracks: [track(0)] });
    render(<TabTransport />);
    expect(screen.queryByRole("button", { name: /capo/i })).toBeNull();
  });

  it("shows the capo fret and turns the capo off for playback", () => {
    usePlayerStore.setState({ tracks: [track(2)] });
    render(<TabTransport />);
    const toggle = screen.getByRole("button", { name: "Capo on (fret 2)" });
    expect(toggle).toHaveTextContent("Capo 2");

    fireEvent.click(toggle);

    expect(changeTrackTranspositionPitch).toHaveBeenCalledWith(
      [api.score!.tracks[0]],
      -2,
    );
    expect(usePlayerStore.getState().capoOn).toBe(false);
    expect(screen.getByRole("button", { name: "Capo off" })).toBeTruthy();
  });
});
