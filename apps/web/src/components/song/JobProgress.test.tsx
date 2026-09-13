import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { queryKeys } from "@/lib/api/queries";
import type { Health, Job } from "@/lib/api/types";
import { makeTestQueryClient, withQueryClient } from "@/test/query";
import { JobProgress } from "@/components/song/JobProgress";
import { mergeTiers } from "@/components/song/tiers";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// openapi-fetch captures globalThis.fetch at import time, so stub the client itself:
// every network call fails and the component must render from the seeded cache.
vi.mock("@/lib/api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api/client")>();
  const offline = async () => ({
    data: undefined,
    error: { title: "Offline", status: 503, detail: "offline" },
    response: new Response(null, { status: 503 }),
  });
  return { ...mod, api: { GET: offline, POST: offline } };
});

const health: Health = {
  status: "ok",
  version: "0.1.0",
  ffmpeg: true,
  ytdlp: false,
  running_jobs: 0,
  tiers: ["songsterr", "ultimate_guitar", "audio"],
  features: {
    spotify: false,
    spotify_user: false,
    spotify_connected: false,
    llm: false,
    songsterr: true,
    ug: true,
    audio: true,
    ytdlp: false,
    separation: false,
    ml_sidecar_ok: false,
    separation_available: false,
    tabcnn_available: false,
    audio_model: "basic-pitch",
    jobs: true,
    musescore: false,
  },
};

const baseJob: Job = {
  id: "job1",
  status: "running",
  request: { song: { raw: "oasis wonderwall" }, capo: 0, cost_profile: "tabgen", origin: "user" },
  song_id: "song1",
  tab_id: null,
  progress: 0.4,
  created_at: "2026-09-11T10:00:00Z",
  updated_at: "2026-09-11T10:00:05Z",
  tiers: [
    {
      tier: "songsterr",
      status: "failed",
      message: "no candidates matched",
      started_at: "2026-09-11T10:00:01Z",
      finished_at: "2026-09-11T10:00:03Z",
      detail: { candidates: [{ songId: 1, title: "Wonderwall", artist: "Oasis", score: 0.4 }], llm_used: true },
    },
    { tier: "ultimate_guitar", status: "running", started_at: "2026-09-11T10:00:03Z", detail: {} },
  ],
};

function renderWithJob(job: Job) {
  const qc = makeTestQueryClient();
  qc.setQueryData(queryKeys.job(job.id), job);
  qc.setQueryData(queryKeys.health, health);
  return render(<JobProgress jobId={job.id} live={false} autoRedirect={false} />, {
    wrapper: withQueryClient(qc),
  });
}

describe("mergeTiers", () => {
  it("orders resolve + health tiers and fills unlogged tiers", () => {
    const tiers = mergeTiers(health.tiers, baseJob);
    expect(tiers.map((t) => t.tier)).toEqual(["resolve", "songsterr", "ultimate_guitar", "audio"]);
    expect(tiers.map((t) => t.status)).toEqual(["success", "failed", "running", "pending"]);
    expect(tiers[3]?.synthetic).toBe(true);
  });

  it("marks unreached tiers skipped on failed jobs and cancelled on cancelled jobs", () => {
    const failed = mergeTiers(health.tiers, { ...baseJob, status: "failed", error: "boom" });
    expect(failed.find((t) => t.tier === "audio")?.status).toBe("skipped");
    const cancelled = mergeTiers(health.tiers, { ...baseJob, status: "cancelled" });
    expect(cancelled.find((t) => t.tier === "audio")?.status).toBe("cancelled");
  });
});

describe("JobProgress", () => {
  it("renders one row per tier with its status, message and LLM badge", () => {
    renderWithJob(baseJob);
    const list = screen.getByRole("list", { name: "Tiers" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-tier"))).toEqual([
      "resolve",
      "songsterr",
      "ultimate_guitar",
      "audio",
    ]);
    expect(rows.map((r) => r.getAttribute("data-status"))).toEqual([
      "success",
      "failed",
      "running",
      "pending",
    ]);
    expect(within(rows[1]!).getByText("no candidates matched")).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/LLM ranked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByText("Running", { selector: "[data-status=running]" })).toBeInTheDocument();
  });

  it("shows the failure card with the audio upload CTA", () => {
    renderWithJob({ ...baseJob, status: "failed", error: "no tab found in any tier", progress: 1 });
    const card = screen.getByTestId("job-failed");
    expect(within(card).getByText("no tab found in any tier")).toBeInTheDocument();
    // Base UI renders `render={<Link>}` buttons as <a role="button">.
    expect(within(card).getByRole("button", { name: /upload audio or paste a url/i })).toHaveAttribute(
      "href",
      "/songs?tab=upload",
    );
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });

  it("shows the success card linking to the tab", () => {
    renderWithJob({ ...baseJob, status: "done", tab_id: "tab9", progress: 1 });
    const card = screen.getByTestId("job-done");
    expect(within(card).getByRole("button", { name: /open tab/i })).toHaveAttribute("href", "/tabs/tab9");
  });
});
