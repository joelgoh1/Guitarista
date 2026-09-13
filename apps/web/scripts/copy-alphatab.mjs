// Copies the alphaTab runtime (ESM entry, worker/worklet scripts, Bravura font,
// sonivox soundfont) from node_modules into public/alphatab/ so the browser can
// load them as plain static assets. Turbopack cannot use alphaTab's webpack/vite
// plugins, so we serve the pre-built dist instead and point `core.scriptFile`
// at it. Runs on `predev` / `prebuild`; the output dir is gitignored.
import { createRequire } from "node:module";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
// The package does not export ./package.json, so resolve the main entry
// (dist/alphaTab.js) and derive the dist directory from it.
const distDir = dirname(require.resolve("@coderline/alphatab"));
const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../public/alphatab");

const files = [
  "alphaTab.mjs",
  "alphaTab.min.mjs",
  "alphaTab.core.mjs",
  "alphaTab.core.min.mjs",
  "alphaTab.worker.mjs",
  "alphaTab.worker.min.mjs",
  "alphaTab.worklet.mjs",
  "alphaTab.worklet.min.mjs",
];
const dirs = ["font", "soundfont"];

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

let copied = 0;
for (const f of files) {
  const src = join(distDir, f);
  if (existsSync(src)) {
    cpSync(src, join(outDir, f));
    copied++;
  }
}
for (const d of dirs) {
  const src = join(distDir, d);
  if (existsSync(src) && statSync(src).isDirectory()) {
    cpSync(src, join(outDir, d), { recursive: true });
    copied++;
  }
}

const version = JSON.parse(readFileSync(join(distDir, "..", "package.json"), "utf8")).version;
console.log(`[copy-alphatab] alphaTab ${version}: copied ${copied} entries -> ${outDir}`);
