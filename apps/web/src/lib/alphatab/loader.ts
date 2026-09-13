/**
 * Runtime loader for alphaTab.
 *
 * We deliberately do NOT bundle `@coderline/alphatab` through Turbopack. When
 * bundled, Turbopack rewrites `import.meta.url` to a `file://` URL, so
 * alphaTab's `Environment._detectWebPlatform()` returns `Browser` instead of
 * `BrowserModule` and it spawns a *classic* worker that `importScripts()` an
 * ES module -> "Cannot use import statement outside a module". Loading the
 * pre-built ESM from `public/alphatab/` (copied by scripts/copy-alphatab.mjs)
 * gives it a real `http(s)://` `import.meta.url`, so the worker and audio
 * worklet resolve `./alphaTab.worker.mjs` / `./alphaTab.worklet.mjs` next to
 * it and run as proper module workers.
 *
 * The npm package is still used for TypeScript types.
 */
import { ALPHATAB_SCRIPT } from "@/lib/alphatab/paths";

export type AlphaTabModule = typeof import("@coderline/alphatab");

let modulePromise: Promise<AlphaTabModule> | null = null;
let loaded: AlphaTabModule | null = null;

export function loadAlphaTab(): Promise<AlphaTabModule> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("alphaTab can only be loaded in the browser"));
  }
  if (!modulePromise) {
    const url = `${window.location.origin}${ALPHATAB_SCRIPT}`;
    modulePromise = (
      import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url) as Promise<AlphaTabModule>
    ).then((mod) => {
      loaded = mod;
      return mod;
    });
    modulePromise.catch(() => {
      modulePromise = null; // allow a retry after a transient failure
    });
  }
  return modulePromise;
}

/** Synchronous accessor; only valid after `loadAlphaTab()` resolved. */
export function getAlphaTab(): AlphaTabModule {
  if (!loaded) throw new Error("alphaTab not loaded yet; await loadAlphaTab() first");
  return loaded;
}
