import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Song → Tab happy path against a fully mocked API. The SSE endpoint is aborted
 * so the job page has to fall back to polling GET /jobs/{id}.
 */
const JOB_ID = "e2ejob0001";
const NEXT_JOB_ID = "e2ejob0002";
const TAB_ID = "e2etab0001";
const SONG_ID = "song1";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "*",
  "access-control-expose-headers": "*",
};

const ALPHATEX = String.raw`\title "Wonderwall"
\artist "Oasis"
\tempo 87
\tuning (e4 b3 g3 d3 a2 e2)
\ts 4 4
.
0.6.4 2.5 2.4 0.3 |
3.2 0.1 3.2 0.3 |
`;

const health = {
  status: "ok",
  version: "e2e",
  ffmpeg: true,
  ytdlp: false,
  running_jobs: 0,
  tiers: ["songsterr", "ultimate_guitar", "audio"],
  features: {
    spotify: false,
    llm: false,
    songsterr: true,
    ug: true,
    audio: true,
    ytdlp: false,
    separation: false,
    ml_sidecar_ok: false,
    separation_available: false,
    jobs: true,
  },
};

const t0 = new Date("2026-09-11T10:00:00Z");
const iso = (offsetS: number) => new Date(t0.getTime() + offsetS * 1000).toISOString();

const request = { song: { raw: "oasis wonderwall" }, capo: 0 };

const jobStates = [
  { id: JOB_ID, status: "queued", request, progress: 0, tiers: [], created_at: iso(0), updated_at: iso(0) },
  {
    id: JOB_ID,
    status: "running",
    request,
    song_id: "song1",
    progress: 0.3,
    tiers: [{ tier: "songsterr", status: "running", started_at: iso(1), detail: {} }],
    created_at: iso(0),
    updated_at: iso(1),
  },
  {
    id: JOB_ID,
    status: "done",
    request,
    song_id: "song1",
    tab_id: TAB_ID,
    progress: 1,
    tiers: [
      {
        tier: "songsterr",
        status: "success",
        started_at: iso(1),
        finished_at: iso(3),
        message: "picked Wonderwall — Oasis (2 tracks)",
        detail: {
          candidates: [{ songId: 1, title: "Wonderwall", artist: "Oasis", score: 0.98 }],
          picked: { songId: 1, title: "Wonderwall", artist: "Oasis" },
          llm_used: false,
          tracks: ["Acoustic Guitar", "Electric Guitar"],
        },
      },
    ],
    created_at: iso(0),
    updated_at: iso(3),
  },
];

const tab = {
  id: TAB_ID,
  song_id: "song1",
  title: "Wonderwall",
  artist: "Oasis",
  source: "songsterr",
  source_ref: "songsterr:1:2:[0, 1]",
  confidence: 0.95,
  tempo_bpm: 87,
  time_signature: { numerator: 4, denominator: 4 },
  tracks: [
    { name: "Acoustic Guitar", instrument: "guitar", tuning: [64, 59, 55, 50, 45, 40], capo: 2, measures: [] },
    { name: "Electric Guitar", instrument: "guitar", tuning: [64, 59, 55, 50, 45, 40], capo: 0, measures: [] },
  ],
  warnings: ["tempo taken from Songsterr metadata"],
  created_at: iso(3),
};

const tabSummaries = [
  { id: TAB_ID, title: "Wonderwall", artist: "Oasis", source: "songsterr", confidence: 0.95, created_at: iso(3), song_id: SONG_ID, track_count: 2 },
  { id: "e2etab0002", title: "Wonderwall", artist: "Oasis", source: "ultimate_guitar", confidence: 0.8, created_at: iso(4), song_id: SONG_ID, track_count: 1 },
];

/** `POST /songs/{id}/candidates` — ordered Songsterr → UG → audio. */
const candidatesResponse = {
  song_id: SONG_ID,
  candidates: [
    { source: "songsterr", external_id: "1", title: "Wonderwall", artist: "Oasis", score: 0.98, kind: null, rating: null, votes: null, track_count: 2, url: "https://www.songsterr.com/a/wsa/-s1", tab_id: TAB_ID, available: true, reason: null },
    { source: "songsterr", external_id: "2", title: "Wonderwall (acoustic)", artist: "Oasis", score: 0.72, kind: null, rating: null, votes: null, track_count: 1, url: null, tab_id: null, available: true, reason: null },
    { source: "ultimate_guitar", external_id: "777", title: "Wonderwall", artist: "Oasis", score: 0.66, kind: "chords", rating: 4.7, votes: 1200, track_count: null, url: null, tab_id: "e2etab0002", available: true, reason: null },
    { source: "ultimate_guitar", external_id: "778", title: "Wonderwall (ver 2)", artist: "Oasis", score: 0.51, kind: "tab", rating: 4.1, votes: 300, track_count: null, url: null, tab_id: null, available: true, reason: null },
    { source: "audio", external_id: "audio", title: "Wonderwall", artist: "Oasis", score: 0, kind: null, rating: null, votes: null, track_count: null, url: null, tab_id: null, available: false, reason: "Upload audio to transcribe" },
  ],
  warnings: ["Ultimate Guitar answered from cache"],
};

const nextJob = {
  id: NEXT_JOB_ID,
  status: "running",
  request: { song_id: SONG_ID, capo: 0 },
  song_id: SONG_ID,
  progress: 0.1,
  tiers: [{ tier: "songsterr", status: "running", started_at: iso(10), detail: {} }],
  created_at: iso(10),
  updated_at: iso(10),
};

function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  return route.fulfill({
    status,
    headers: { "content-type": "application/json", ...CORS, ...headers },
    body: JSON.stringify(body),
  });
}

interface MockState {
  /** Bodies of every `POST /jobs`, in order. */
  jobRequests: Record<string, unknown>[];
}

async function mockApi(page: Page): Promise<MockState> {
  let jobPolls = 0;
  let jobCreated = false;
  const state: MockState = { jobRequests: [] };


  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });

    if (path === "/health") return json(route, health);
    if (path === "/tabs") return json(route, url.searchParams.get("song_id") === SONG_ID ? tabSummaries : []);
    if (path === "/jobs" && req.method() === "GET") return json(route, jobCreated ? [jobStates[2]] : []);
    if (path === "/jobs" && req.method() === "POST") {
      const body = req.postDataJSON() as Record<string, unknown>;
      state.jobRequests.push(body);
      if (Array.isArray(body.exclude) || body.candidate) return json(route, nextJob, 201);
      jobCreated = true;
      expect(body).toMatchObject({ song: { raw: "oasis wonderwall" } });
      return json(route, jobStates[0], 201);
    }
    if (path === `/jobs/${JOB_ID}/events` || path === `/jobs/${NEXT_JOB_ID}/events`) return route.abort("connectionrefused");
    if (path === `/jobs/${NEXT_JOB_ID}`) return json(route, nextJob);
    if (path === `/jobs/${JOB_ID}`) {
      const state = jobStates[Math.min(jobPolls, jobStates.length - 1)];
      jobPolls += 1;
      return json(route, state);
    }
    if (path === `/tabs/${TAB_ID}`) {
      if (url.searchParams.get("format") === "alphatex") {
        return route.fulfill({
          status: 200,
          headers: { "content-type": "text/x-alphatex; charset=utf-8", ...CORS },
          body: ALPHATEX,
        });
      }
      return json(route, tab);
    }
    return json(route, { title: "Not Found", status: 404, detail: `unmocked ${path}` }, 404);
  });

  // Candidates listing. Registered after the catch-all: Playwright matches the most
  // recently added route first, so this one wins for `/songs/{id}/candidates`.
  await page.route("**/songs/*/candidates", async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    expect(route.request().url()).toContain(`/songs/${SONG_ID}/candidates`);
    return json(route, candidatesResponse);
  });
  return state;
}

test("raw text → job timeline (polling fallback) → redirect → alphaTab renders", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  const mocks = await mockApi(page);

  await page.goto("/songs");
  await page.getByLabel("Spotify link or song text").fill("oasis wonderwall");
  await expect(page.getByText(/Searching tab sources for/)).toBeVisible();
  await page.getByRole("button", { name: "Find tab" }).click();

  await expect(page).toHaveURL(new RegExp(`/songs/${JOB_ID}$`));
  const tiers = page.getByRole("list", { name: "Tiers" });
  await expect(tiers.locator('[data-tier="songsterr"]')).toHaveAttribute("data-status", "success");
  await expect(page.getByText("picked Wonderwall — Oasis (2 tracks)")).toBeVisible();
  await expect(page.getByTestId("job-done")).toContainText("Wonderwall");

  await expect(page).toHaveURL(new RegExp(`/tabs/${TAB_ID}`), { timeout: 15_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Wonderwall" })).toBeVisible();
  await expect(page.locator(".at-surface svg").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("toolbar", { name: "Playback" })).toBeVisible();
  // Track selector present for the 2-track tab; MusicXML download points at the API.
  await expect(page.getByRole("combobox", { name: "Track" })).toBeVisible();
  // Base UI renders `render={<a>}` buttons with role="button".
  await expect(page.getByRole("button", { name: /MusicXML/ })).toHaveAttribute("href", /format=musicxml/);

  // ---- Other versions drawer ----
  // Two stored tabs for this song → "2 versions" chip; it opens the same drawer as the header button.
  await expect(page.getByTestId("version-count")).toHaveText(/2 versions/);
  await page.getByRole("button", { name: /Other versions/ }).click();
  const drawer = page.getByTestId("other-versions");
  await expect(drawer).toBeVisible();
  // Grouped Songsterr → Ultimate Guitar → Audio.
  await expect(drawer.locator("[data-source-group]")).toHaveCount(3);
  const groupOrder = await drawer.locator("[data-source-group]").evaluateAll((els) => els.map((e) => e.getAttribute("data-source-group")));
  expect(groupOrder).toEqual(["songsterr", "ultimate_guitar", "audio"]);
  await expect(drawer.getByRole("list", { name: "Songsterr versions" }).getByRole("listitem")).toHaveCount(2);
  await expect(drawer.getByRole("list", { name: "Ultimate Guitar versions" }).getByRole("listitem")).toHaveCount(2);
  // The open tab is marked current; UG row carries its badges; audio is unavailable with an upload link.
  await expect(drawer.locator('[data-candidate="songsterr:1"]')).toHaveAttribute("data-current", "true");
  await expect(drawer.locator('[data-candidate="songsterr:1"]').getByText("Current", { exact: true })).toBeVisible();
  await expect(drawer.locator('[data-candidate="ultimate_guitar:777"]').getByText("chords")).toBeVisible();
  await expect(drawer.locator('[data-candidate="ultimate_guitar:777"]').getByRole("button", { name: "Open" })).toHaveAttribute("href", "/tabs/e2etab0002");
  await expect(drawer.locator('[data-candidate="audio:audio"]').getByRole("button", { name: /Fetch this version/ })).toBeDisabled();
  await expect(drawer.locator('[data-candidate="audio:audio"]').getByRole("button", { name: /Upload audio/ })).toHaveAttribute("href", "/songs?tab=upload");
  await expect(drawer.getByRole("button", { name: /1 warning/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // ---- "Not this one, next" → POST /jobs with an exclude array of every tried version ----
  await page.getByTestId("next-version").click();
  await expect(page).toHaveURL(new RegExp(`/songs/${NEXT_JOB_ID}$`));
  const nextRequest = mocks.jobRequests.at(-1)!;
  expect(nextRequest.song_id).toBe(SONG_ID);
  expect(nextRequest.exclude).toEqual([
    { source: "songsterr", external_id: "1" },
    { source: "ultimate_guitar", external_id: "777" },
  ]);
  // The exclusion list is remembered per song for the next click.
  const stored = await page.evaluate((id) => window.sessionStorage.getItem(`guitarista:exclusions:${id}`), SONG_ID);
  expect(JSON.parse(stored!)).toEqual(nextRequest.exclude);

  // The SSE route is aborted on purpose (polling fallback) → Chromium logs one net:: error for it.
  const relevant = errors.filter((e) => !/favicon/i.test(e) && !/net::ERR_/.test(e));
  expect(relevant, relevant.join("\n")).toEqual([]);
});
