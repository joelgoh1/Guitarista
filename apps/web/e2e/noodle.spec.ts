import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Noodle mode on the home page against a fully mocked API: the listening shelf
 * renders the pool, and "Surprise me" opens the ready tab.
 */
const READY_TAB_ID = "e2enoodletab1";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
  "access-control-allow-headers": "*",
  "access-control-expose-headers": "*",
};

const health = {
  status: "ok",
  version: "e2e",
  ffmpeg: true,
  ytdlp: false,
  running_jobs: 0,
  tiers: ["songsterr", "ultimate_guitar", "audio"],
  features: {
    spotify: true,
    spotify_user: true,
    spotify_connected: true,
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

const evidence = (partial: Record<string, unknown> = {}) => ({
  top_short: null,
  top_medium: null,
  top_long: null,
  recent: 0,
  liked: false,
  ...partial,
});

const readyEntry = {
  spotify_id: "sp_ready",
  title: "Wonderwall",
  artist: "Oasis",
  album: "(What's the Story) Morning Glory?",
  artwork_url: null,
  duration_ms: 258000,
  evidence: evidence({ top_short: 0 }),
  score: 0.98,
  availability: "available",
  candidate: null,
  song_id: "song1",
  tab_id: READY_TAB_ID,
  job_id: null,
  status: "ready",
  error: null,
  attempts: 0,
  refreshed_at: null,
};

const newEntry = {
  spotify_id: "sp_new",
  title: "Black Hole Sun",
  artist: "Soundgarden",
  album: "Superunknown",
  artwork_url: null,
  duration_ms: 318000,
  evidence: evidence({ liked: true }),
  score: 0.4,
  availability: "available",
  candidate: {
    source: "songsterr",
    external_id: "99",
    title: "Black Hole Sun",
    artist: "Soundgarden",
    score: 0.9,
    available: true,
  },
  song_id: null,
  tab_id: null,
  job_id: null,
  status: "new",
  error: null,
  attempts: 0,
  refreshed_at: null,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    headers: { "content-type": "application/json", ...CORS },
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });

    if (path === "/health") return json(route, health);
    if (path === "/tabs") return json(route, []);
    if (path === "/jobs" && req.method() === "GET") return json(route, []);
    if (path === "/recommendations") return json(route, [readyEntry, newEntry]);
    if (path === "/recommendations/surprise") {
      return json(route, { entry: readyEntry, tab_id: READY_TAB_ID, reason: "On repeat" });
    }
    // The tab page itself is not under test; keep it minimal so the route resolves.
    if (path === `/tabs/${READY_TAB_ID}`) {
      return json(route, { title: "Not Found", status: 404, detail: "tab not mocked" }, 404);
    }
    return json(route, { title: "Not Found", status: 404, detail: `unmocked ${path}` }, 404);
  });
}

test("listening shelf renders the pool and Surprise me opens the ready tab", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const shelf = page.getByTestId("listening-shelf");
  await expect(shelf).toBeVisible();
  const cards = shelf.getByTestId("noodle-card");
  await expect(cards).toHaveCount(2);

  // Ready entry links straight at its tab and carries its evidence chip.
  const ready = cards.filter({ hasText: "Wonderwall" });
  await expect(ready).toHaveAttribute("data-status", "ready");
  await expect(ready).toHaveAttribute("href", `/tabs/${READY_TAB_ID}`);
  await expect(ready.getByTestId("evidence")).toHaveText("On repeat");

  // The new entry offers a Generate button plus a dismiss control.
  const fresh = cards.filter({ hasText: "Black Hole Sun" });
  await expect(fresh).toHaveAttribute("data-status", "new");
  await expect(fresh.getByTestId("generate")).toBeVisible();
  await expect(fresh.getByTestId("evidence")).toHaveText("Liked");
  await expect(fresh.getByRole("button", { name: "Dismiss Black Hole Sun" })).toBeVisible();

  await page.getByTestId("surprise").click();
  await expect(page).toHaveURL(new RegExp(`/tabs/${READY_TAB_ID}$`));
});
