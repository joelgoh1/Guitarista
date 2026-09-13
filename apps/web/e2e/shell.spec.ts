import { expect, test } from "@playwright/test";

test("home renders the shell navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Any song");
  const nav = page.locator('[data-sidebar="content"]');
  for (const label of ["Home", "Song → Tab", "Score → Tab", "Chords", "Library", "Practice", "Improv"]) {
    await expect(nav.getByRole("link", { name: new RegExp(label) })).toBeVisible();
  }
});

test("demo tab renders alphaTab SVG without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));

  await page.goto("/tabs/demo");
  await expect(page.locator(".at-surface svg").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("toolbar", { name: "Playback" })).toBeVisible();
  // Play button becomes enabled once the soundfont has loaded.
  await expect(page.getByRole("button", { name: "Play" })).toBeEnabled({ timeout: 30_000 });

  expect(errors, errors.join("\n")).toEqual([]);
});
