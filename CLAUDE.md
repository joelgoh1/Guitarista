# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Guitarista is a guitar super app: song → tab (flagship), score → tab, and a chord trainer. Monorepo, local-only,
no auth. See `README.md` for the user-facing overview and `/Users/joel/.claude/plans/context-i-want-a-jiggly-canyon.md`
for the original rewrite plan. The pre-2026 Vite/Flask prototype was deleted; only the chord JSON survived.

## Layout and commands

| Path | Stack | Run |
|---|---|---|
| `apps/web` | Next.js 16 (App Router, Turbopack), React 19, Tailwind v4, shadcn (base-nova preset, Base UI primitives), TanStack Query, zustand, nuqs, Dexie, alphaTab, smplr | `pnpm --filter web dev|build|lint|typecheck|test|test:e2e` |
| `apps/api` | FastAPI, Python 3.12, uv, Pydantic v2, SQLAlchemy 2 async + aiosqlite + Alembic, httpx, sse-starlette, music21, rapidfuzz | `cd apps/api && uv run uvicorn guitarista_api.main:app --reload --port 8000`; `uv run pytest -q`; `uv run ruff check .`; `uv run mypy src` |
| `apps/ml` | Python 3.11 sidecar CLI `guitarista-ml` (basic-pitch CoreML; optional Demucs via `uv sync --extra separate`) | `cd apps/ml && uv run guitarista-ml probe`; `uv run pytest -q` |
| `packages/tab-model` | zod schema of the canonical Tab JSON (+ `tab.schema.json` exported from Pydantic) | `pnpm --filter @guitarista/tab-model test` |
| `packages/music-theory` | note/scale utils, chord library data (`data/*.json`) | `pnpm --filter @guitarista/music-theory test` |
| `packages/api-types` | `openapi-typescript` output; regenerate with `pnpm --filter @guitarista/api gen:api` after changing any router/model | committed |
| `packages/config` | shared tsconfig | |

Root: `pnpm dev|build|lint|typecheck|test` (turbo). `make setup` installs everything and copies `.env.example` to `.env`
and `apps/api/.env`. Settings are read with prefix `GUITARISTA_` (see `apps/api/src/guitarista_api/settings.py`).

## Architecture

**Song → tab is a tier chain, not an agent.** `jobs/runner.py` resolves the song (Spotify if creds, else raw text), then
`services/tier_runner.py` walks `services/sources_factory.build_sources()`: `SongsterrSource` → `UltimateGuitarSource` →
`AudioSource`. Each implements `sources/base.TabSource` (`can_handle` returns a skip reason, `fetch` returns a
`SourceResult`), has its own timeout from settings, and logs a `TierLogEntry` (statuses pending/skipped/running/success/
failed/timeout/cancelled). First success wins. `JobManager` (`jobs/manager.py`) is an in-process asyncio task registry
that persists every change to SQLite and fans out SSE events on `GET /api/v1/jobs/{id}/events`; every event payload
carries a full `job` snapshot so the client just replaces state. Jobs left running at boot are marked `interrupted`.

**LLM is optional and narrow.** `adapters/llm.py::OpenRouterLLM` (default model `qwen/qwen3.8-flash`) is only called for
`rank_candidates` (when fuzzy ranking is ambiguous), `rewrite_query` (zero search results), `extract_tab_text` (UG ASCII
parse yields too few notes). No key → `app.state.llm is None` and everything is deterministic.

**Canonical Tab JSON** (`domain/tab.py`, mirrored by `packages/tab-model`): `string` 1 = highest-pitched string,
`tuning` is a MIDI list for strings 1..N (high→low), durations are fractions of a whole note (`Duration{num,den,dots,tuplet}`).
`domain/validate.py::validate_tab` enforces `tuning[string-1] + capo + fret == pitch_midi`. All exporters live in
`services/export/`: **alphaTex is the render format** (`GET /tabs/{id}?format=alphatex&track=N`, one track per call),
MusicXML for download, ASCII for debugging.

**Fretting solver** (`solver/`, pure Python, no IO): `candidates.enumerate_frettings` → `cost.BaselineCost` (tabgen
heuristics: movement, spread, skipped strings, high-fret penalty, open-string bonus) → `search.solve` (exact Viterbi by
default, beam kept for context-dependent costs). Shared by score→tab and the audio tier; `quantize.py` turns basic-pitch
note events into chord events first.

**Audio tier** never imports torch/tensorflow. `adapters/ml_sidecar.py` shells out to `apps/ml` (`settings.ml_cmd`, default
`uv run --directory ../ml guitarista-ml`), parses JSON on stdout and progress lines on stderr. ffmpeg converts uploads to
mono 22 kHz wav first. yt-dlp is off by default (`GUITARISTA_ENABLE_YTDLP`), Demucs behind `GUITARISTA_ENABLE_SEPARATION`.
Audio comes from one of three places, in order: `TabRequest.upload_id` (a file on disk), `TabRequest.audio_url` (downloaded
verbatim, no search), or a YouTube search. The search never blindly takes the top hit -- `adapters/ytdlp.search_candidates`
lists five hits metadata-only and `services/yt_match.pick_best` scores them on title fuzz (reusing `ranking.score_candidate`)
plus agreement with Spotify's `Song.duration_s`, rejecting covers/live cuts/full-album uploads outright; with no acceptable
match the tier fails loudly rather than transcribing the wrong recording. Every candidate's breakdown lands in the tier log's
`detail["input"]["considered"]`.

**Frontend.** Browser talks to FastAPI directly (CORS allows `localhost:3000`); a Next rewrite for `/api/*` exists as a
convenience. `src/lib/api/queries.ts` holds `queryOptions` factories; `src/lib/api/sse.ts` + `hooks/useJobEvents.ts` write SSE
snapshots into the job query cache and fall back to polling. Backend SQLite is the library; Dexie (`src/lib/db`) only stores
per-tab playback progress and settings. Design tokens live only in `src/app/globals.css` (dark-first, oklch); components
use semantic Tailwind utilities, never color literals.

**Noodle mode (Spotify listening → suggested tabs).** Optional user login via Authorization Code + PKCE
(`adapters/spotify_user.py::SpotifyUserClient`, router `api/spotify.py`: `/spotify/login|callback|status`, `DELETE /spotify/auth`);
the single refresh token lives in the `spotify_auth` table. `services/listening_pool.py::build_pool` pulls top tracks
(short/medium/long), recently played (max 50) and liked songs, merges them by Spotify id into `listening_pool` rows with a
pure `score_entry`, marks songs that already have a tab `ready`, and probes Songsterr availability via
`SongsterrSource.candidates`. `jobs/prefetch.py::NoodlePrefetcher` (one asyncio task, started in lifespan when connected)
tops the pool up to `noodle_prefetch_target` ready tabs, one Songsterr-only job at a time and only when no user job is running,
through `services/job_launch.py::launch_tab_job` (shared with `POST /jobs`) with `TabRequest.origin="noodle"`.
`api/recommendations.py` exposes the pool, `/refresh`, `/{id}/dismiss` and `/surprise`. Spotify's own Recommendations /
Related Artists endpoints are gone for new apps, so the pool is strictly the user's own history. Web: `/settings` Spotify card,
`components/noodle/` shelf + Surprise button, gated on `features.spotify_connected`.

## Gotchas

- **alphaTab is not bundled.** Turbopack rewrites `import.meta.url` to `file://`, which breaks alphaTab's worker spawning.
  `scripts/copy-alphatab.mjs` (runs on `predev`/`prebuild`) copies `dist/` to `public/alphatab/` and `src/lib/alphatab/loader.ts`
  dynamically imports it from there. The npm package is types-only at runtime. Details: `apps/web/docs/alphatab-notes.md`.
- **alphaTex string numbers**: in alphaTex text, string 1 = highest string (same as our canonical model), so the Python
  exporter emits strings unchanged. alphaTab's in-memory `Note.string` is the opposite (1 = lowest); flip only when reading
  model objects in the browser (`packages/tab-model/src/alphatab-strings.ts`). A pin test guards this.
- alphaTab's color parser rejects `oklch()`; `src/lib/alphatab/colors.ts` resolves tokens through a canvas first.
- Base UI `Button` with `render={<Link/>}` needs `nativeButton={false}`; use `buttonVariants()` on a plain `Link` otherwise.
- Workspace packages are consumed as source via `transpilePackages`; relative imports inside them must not use `.js` suffixes
  (Turbopack cannot resolve them).
- Songsterr and Ultimate Guitar are unofficial. Recorded fixtures with the real shapes live in `apps/api/tests/fixtures/{songsterr,ug}`;
  Songsterr tempo is in `automations.tempo[]`, capo is top-level, note `string` is 0-based with 0 = highest, rests are beat-level.
- basic-pitch has no Python 3.12 wheels, hence the separate 3.11 `apps/ml` project; it also needs `setuptools<81` (pkg_resources).
- `uv` prints a `VIRTUAL_ENV` mismatch warning because a conda env is active in the shell; ignore it.
- `TierName` includes `resolve`; the resolve step logs its own tier entry before the sources run.
- **Score import beyond MusicXML/MIDI goes through MuseScore.** `adapters/musescore.py` shells out to `mscore -o out.musicxml in.mscz`
  to accept `.mscz`/`.mscx`/Guitar Pro/Capella (`MUSESCORE_SUFFIXES` in `adapters/score_import.py`). It is optional and
  auto-detected (macOS `.app` bundle paths included) via `settings.mscore_bin`; `/health` reports `features.musescore` and the
  web dropzone only advertises those formats when it is true. Conversion happens **once, at upload**, so `UploadRow.path` points
  at the generated `.musicxml` while `UploadRow.filename` keeps the user's original extension — everything downstream of the
  upload only ever sees music21-native files.
- Do **not** force `QT_QPA_PLATFORM=offscreen` on macOS: MuseScore ships only the `cocoa` plugin there and refuses to start.
  `musescore._env()` sets it on Linux only. mscore also prints ~40 lines of Qt/QML noise to stderr on success, and can exit 0
  while writing nothing — the output file is the only reliable success signal.
- Spotify redirect URI must be a loopback literal, not `localhost`: default `GUITARISTA_SPOTIFY_REDIRECT_URI` is
  `http://127.0.0.1:8000/api/v1/spotify/callback` and must match the dashboard exactly. Dev-mode apps also need the account
  allowlisted under Users & Access, or the callback fails with 403. `spotify_user_enabled` (client id only) is distinct from
  `spotify_enabled` (id + secret, client-credentials search).
- `db/repos_noodle.py` uses a `PoolEntries` alias because `PoolRepo.list` shadows the `list` builtin under mypy; keep it.
