import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { queryKeys } from "@/lib/api/queries";
import type { Candidate, CandidatesResponse } from "@/lib/api/types";
import { makeTestQueryClient, withQueryClient } from "@/test/query";
import { OtherVersionsBody } from "@/components/song/OtherVersions";
import { clearExclusions, saveExclusions } from "@/components/song/versions";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

const postMock = vi.fn();
vi.mock("@/lib/api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/client")>();
  const offline = async () => ({
    data: undefined,
    error: { title: "Offline", status: 503, detail: "offline" },
    response: new Response(null, { status: 503 }),
  });
  return {
    ...mod,
    api: {
      GET: offline,
      // Candidate listings come from the seeded cache; only job creation is answered.
      POST: (path: string, ...rest: unknown[]) => (path === "/api/v1/jobs" ? postMock(path, ...rest) : offline()),
    },
  };
});

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

const response: CandidatesResponse = {
  song_id: "song1",
  candidates: [
    candidate({ source: "songsterr", external_id: "1", tab_id: "tab1", score: 0.98, track_count: 2, url: "https://songsterr.example/1" }),
    candidate({ source: "songsterr", external_id: "2", title: "Wonderwall (acoustic)", score: 0.7, track_count: 1 }),
    candidate({ source: "ultimate_guitar", external_id: "777", kind: "chords", rating: 4.7, votes: 1200, score: 0.6 }),
    candidate({ source: "audio", external_id: "audio", available: false, reason: "Upload audio to transcribe", score: 0 }),
  ],
  warnings: ["Ultimate Guitar rate limited; showing cached results"],
};

const currentTab = { id: "tab1", source: "songsterr" as const, source_ref: "songsterr:1:2:[0, 1]" };

function renderBody(data: CandidatesResponse | null = response) {
  const qc = makeTestQueryClient();
  if (data) qc.setQueryData(queryKeys.candidates("song1"), data);
  return render(<OtherVersionsBody songId="song1" currentTab={currentTab} />, { wrapper: withQueryClient(qc) });
}

beforeEach(() => {
  postMock.mockReset();
  push.mockReset();
  clearExclusions("song1");
});
afterEach(() => clearExclusions("song1"));

describe("OtherVersionsBody", () => {
  it("renders candidates grouped by source with badges, current marker and actions", () => {
    renderBody();

    const songsterr = screen.getByRole("list", { name: "Songsterr versions" });
    const ug = screen.getByRole("list", { name: "Ultimate Guitar versions" });
    const audio = screen.getByRole("list", { name: "Audio versions" });
    expect(within(songsterr).getAllByRole("listitem")).toHaveLength(2);
    expect(within(ug).getAllByRole("listitem")).toHaveLength(1);
    expect(within(audio).getAllByRole("listitem")).toHaveLength(1);

    // Current version: marked and linked (Base UI renders render={<Link>} as <a role="button">).
    const current = songsterr.querySelector('[data-candidate="songsterr:1"]')!;
    expect(current).toHaveAttribute("data-current", "true");
    expect(within(current as HTMLElement).getByText("Current")).toBeInTheDocument();
    expect(within(current as HTMLElement).getByRole("button", { name: /open \(current\)/i })).toHaveAttribute("href", "/tabs/tab1");
    expect(within(current as HTMLElement).getByText("2 tracks")).toBeInTheDocument();
    expect(within(current as HTMLElement).getByText("98%")).toBeInTheDocument();

    // Not-yet-fetched version offers "Fetch this version".
    const second = songsterr.querySelector('[data-candidate="songsterr:2"]') as HTMLElement;
    expect(within(second).getByRole("button", { name: /fetch this version/i })).toBeEnabled();

    // UG badges: kind + rating/votes.
    expect(within(ug).getByText("chords")).toBeInTheDocument();
    expect(within(ug).getByText(/4\.7/)).toBeInTheDocument();
    expect(within(ug).getByText("(1200)")).toBeInTheDocument();

    // Unavailable audio: disabled fetch, reason, upload link.
    const audioRow = within(audio).getByRole("listitem");
    expect(within(audioRow).getByRole("button", { name: /fetch this version/i })).toBeDisabled();
    expect(within(audioRow).getByText("Upload audio to transcribe")).toBeInTheDocument();
    expect(within(audioRow).getByRole("button", { name: /upload audio/i })).toHaveAttribute("href", "/songs?tab=upload");

    // Warnings collapsed by default.
    const toggle = screen.getByRole("button", { name: /1 warning/ });
    expect(screen.queryByText(/rate limited/)).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText(/rate limited/)).toBeInTheDocument();
  });

  it("shows skeletons while loading", () => {
    renderBody(null);
    expect(screen.getByTestId("candidates-loading")).toBeInTheDocument();
  });

  it("fetches a specific candidate and navigates to the job", async () => {
    postMock.mockResolvedValue({
      data: { id: "job2", status: "queued", request: { capo: 0 }, progress: 0 },
      error: undefined,
      response: new Response(null, { status: 201 }),
    });
    renderBody();
    const second = screen.getByRole("list", { name: "Songsterr versions" }).querySelector('[data-candidate="songsterr:2"]') as HTMLElement;
    fireEvent.click(within(second).getByRole("button", { name: /fetch this version/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/songs/job2"));
    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/jobs",
      expect.objectContaining({
        body: expect.objectContaining({ song_id: "song1", candidate: { source: "songsterr", external_id: "2" } }),
      }),
    );
  });

  it("'Not this one, next' excludes every tried version and remembers them", async () => {
    postMock.mockResolvedValue({
      data: { id: "job3", status: "queued", request: { capo: 0 }, progress: 0, song_id: "song1" },
      error: undefined,
      response: new Response(null, { status: 201 }),
    });
    saveExclusions("song1", [{ source: "ultimate_guitar", external_id: "778" }]);
    renderBody();
    expect(screen.getByTestId("skipped-count")).toHaveTextContent("1 version skipped so far");

    fireEvent.click(screen.getByRole("button", { name: /not this one, next/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/songs/job3"));
    const body = (postMock.mock.calls[0]![1] as { body: { song_id: string; exclude: unknown[] } }).body;
    expect(body.song_id).toBe("song1");
    expect(body.exclude).toEqual([
      { source: "ultimate_guitar", external_id: "778" },
      { source: "songsterr", external_id: "1" },
    ]);
    expect(JSON.parse(window.sessionStorage.getItem("guitarista:exclusions:song1")!)).toEqual(body.exclude);
    expect(screen.getByTestId("skipped-count")).toHaveTextContent("2 versions skipped so far");

    fireEvent.click(screen.getByRole("button", { name: /start over/i }));
    expect(screen.getByTestId("skipped-count")).toHaveTextContent("Nothing skipped yet");
    expect(window.sessionStorage.getItem("guitarista:exclusions:song1")).toBeNull();
  });
});
