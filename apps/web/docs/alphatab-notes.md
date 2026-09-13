# alphaTab under Next 16 / Turbopack

Outcome of the phase-2 spike (alphaTab 1.8.4, Next 16.3.4, Turbopack, React 19.2).

## TL;DR

- **Do not bundle alphaTab.** Load the pre-built ESM from `public/alphatab/alphaTab.mjs`
  at runtime (`src/lib/alphatab/loader.ts`) and use the npm package for types only.
- With that, **workers and the AudioWorklet work out of the box** — no fallback needed.
  `/tabs/demo` renders SVG, loads `sonivox.sf3`, and plays with the cursor in Chromium
  with zero console errors (`e2e/shell.spec.ts` asserts this).
- The env fallback still exists: `NEXT_PUBLIC_ALPHATAB_WORKERS=false` renders on the main
  thread and switches audio output to `PlayerOutputMode.WebAudioScriptProcessor`.

## What failed first

Importing `@coderline/alphatab` normally (bundled by Turbopack) produced:

```
Failed to execute 'importScripts' on 'WorkerGlobalScope': Cannot use import statement outside a module
```

Root cause (see `dist/alphaTab.core.mjs`, `Environment._detectWebPlatform`):
alphaTab checks `import.meta.url`; if it is a non-`file://` URL it treats itself as
`WebPlatform.BrowserModule` and spawns `new Worker(new URL('./alphaTab.worker.mjs', import.meta.url), { type: 'module' })`.
Turbopack rewrites `import.meta.url` to a `file:///…` path, so detection falls back to
`WebPlatform.Browser`, which creates a **classic** blob worker doing
`importScripts(settings.core.scriptFile)` — and `alphaTab.mjs` is an ES module, so that throws.
Forcing `Environment.webPlatform = BrowserModule` would not help either: the sibling-URL
resolution would still be relative to Turbopack's bogus `import.meta.url`.

alphaTab's own webpack/vite plugins solve this for those bundlers; there is no Turbopack plugin.

## What works

`scripts/copy-alphatab.mjs` (runs on `predev`/`prebuild`, output gitignored) copies
`dist/{alphaTab,alphaTab.core,alphaTab.worker,alphaTab.worklet}(.min).mjs`, `font/`, `soundfont/`
into `public/alphatab/`. The client does

```ts
import(/* webpackIgnore: true */ /* turbopackIgnore: true */ `${location.origin}/alphatab/alphaTab.mjs`)
```

so `import.meta.url` inside alphaTab is the real `http://…/alphatab/alphaTab.mjs`; the worker and
worklet resolve `./alphaTab.worker.mjs` / `./alphaTab.worklet.mjs` beside it. Side benefit: the
~1.5 MB alphaTab bundle is not part of the Next build output.

Settings (`src/lib/alphatab/settings.ts`):

- `core.scriptFile = ${origin}/alphatab/alphaTab.mjs` (absolute; used by alphaTab's fallbacks)
- `core.fontDirectory = /alphatab/font/` (Bravura)
- `core.engine = 'svg'`, `core.useWorkers` from env
- `player.soundFont = /alphatab/soundfont/sonivox.sf3`, `enablePlayer/enableCursor/enableUserInteraction`
- `player.outputMode` = worklets when workers are on, ScriptProcessor otherwise
- `display.resources.*` colors are read from CSS tokens (`--tab-glyph`, `--tab-glyph-secondary`,
  `--tab-staff-line`) via a 1×1 canvas (`src/lib/alphatab/colors.ts`) because alphaTab's `Color`
  parser does not understand `oklch()`. Cursor/highlight colors are plain CSS in `globals.css`
  (`.at-cursor-bar`, `.at-cursor-beat`, `.at-highlight *`, `.at-selection div`).

## Gotchas noted

- alphaTex: `\text` is not metadata; beat text is `{txt "…"}`. Parse errors surface via `api.error`.
- The AlphaTabApi is not serialisable: it lives in a React context (`PlayerApiProvider`), the
  zustand `player` store only mirrors transport state.
- React Compiler lint (`react-hooks/immutability`) forbids assigning to the api object from
  components; all mutations go through `src/lib/alphatab/controls.ts`.
- StrictMode double-invokes effects: the viewer destroys the instance in cleanup before
  re-creating it, and the async runtime load is guarded with a `cancelled` flag.
- Playback requires a user gesture for the AudioContext; the transport's Play button (or Space)
  provides it.
- alphaTab string numbering (`1` = lowest string in alphaTex `fret.string`) still needs the
  pinned test in `packages/tab-model` before the Python exporter relies on it.
