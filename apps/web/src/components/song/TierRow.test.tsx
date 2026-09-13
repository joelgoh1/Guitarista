import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TierRow } from "@/components/song/TierRow";
import type { TierView } from "@/components/song/tiers";

function audioTier(detail: Record<string, unknown>): TierView {
  return {
    tier: "audio",
    label: "Audio",
    description: "Transcribe from audio",
    status: "success",
    message: "transcribed 120 notes",
    detail,
    started_at: null,
    finished_at: null,
  } as TierView;
}

async function openDetails(detail: Record<string, unknown>) {
  const { container } = render(
    <ul>
      <TierRow tier={audioTier(detail)} now={Date.now()} isLast />
    </ul>,
  );
  fireEvent.click(screen.getByRole("button", { name: /details/i }));
  // Scope to the tier row itself; the runners-up render their own list items inside it.
  const row = container.querySelector<HTMLElement>('[data-tier="audio"]')!;
  // The detail panel animates open.
  await waitFor(() => expect(row.querySelector("pre, a, p")).toBeTruthy());
  return row;
}

describe("TierRow audio input", () => {
  it("shows which video was matched, with its duration against the expected one", async () => {
    const row = await openDetails({
      input: {
        kind: "ytdlp",
        url: "https://www.youtube.com/watch?v=FVdjZYfDuLE",
        title: "Wonderwall (Remastered)",
        uploader: "Oasis",
        duration_s: 259,
        expected_duration_s: 258.9,
        considered: [
          { video_id: "FVdjZYfDuLE", title: "Wonderwall (Remastered)", score: 1 },
          { video_id: "loop", title: "Wonderwall [10 HOURS]", score: 0, rejected: "duration off by 35741s" },
        ],
      },
    });
    const link = within(row).getByRole("link", { name: "Wonderwall (Remastered)" });
    expect(link).toHaveAttribute("href", "https://www.youtube.com/watch?v=FVdjZYfDuLE");
    expect(within(row).getByText(/expected/i)).toBeInTheDocument();
    // Runners-up are listed so a wrong pick is explainable.
    expect(within(row).getByText(/duration off by 35741s/)).toBeInTheDocument();
  });

  it("labels an explicit URL differently and skips match scoring", async () => {
    const row = await openDetails({
      input: { kind: "ytdlp_url", url: "https://youtu.be/abc", file: "ytdlp.wav" },
    });
    expect(within(row).getByText(/audio from url/i)).toBeInTheDocument();
    expect(within(row).queryByText(/expected/i)).toBeNull();
  });

  it("still dumps non-ytdlp input rather than dropping it", async () => {
    const row = await openDetails({
      input: { kind: "upload", upload_id: "abc123", filename: "riff.wav" },
    });
    expect(within(row).getByText(/riff\.wav/)).toBeInTheDocument();
  });
});
