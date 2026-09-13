# Guitarista

A guitar super app: turn songs into playable tabs, convert scores to tablature, and learn chords.

## Layout

| Path | What |
|---|---|
| `apps/web` | Next.js 16 app (App Router, Tailwind v4, shadcn/ui, alphaTab for tab rendering + playback) |
| `apps/api` | FastAPI backend (Python 3.12, uv): song → tab pipeline, fretting solver, score import, SQLite |
| `apps/ml` | ML sidecar CLI (Python 3.11, uv): basic-pitch transcription, optional Demucs guitar-stem separation |
| `packages/tab-model` | zod schema + TS types for the canonical Tab JSON |
| `packages/music-theory` | note/chord/scale utilities + chord library data |
| `packages/api-types` | OpenAPI types generated from the backend |
| `packages/config` | shared tsconfig / eslint presets |

## Quick start (macOS)

```bash
brew install uv ffmpeg yt-dlp        # yt-dlp optional
corepack enable
make setup                            # pnpm install + uv sync for api and ml, copies .env.example → .env
make dev                              # turbo: web on :3000, api on :8000
```

Optional keys go in `.env` / `apps/api/.env`: Spotify client credentials (song resolution) and an
OpenRouter key (LLM assist for ranking/extraction). Everything works without them; those tiers are skipped.

## Getting scores to convert

Score → tab reads **MusicXML** (`.musicxml`, `.xml`, `.mxl`) and **MIDI** out of the box. Install
[MuseScore Studio](https://musescore.org/download) — free and open source — and it additionally accepts
`.mscz`/`.mscx`, **Guitar Pro** (`.gp3/.gp4/.gp5/.gpx/.gp`) and Capella files, converting them on upload.
`/health` reports whether it was found; set `GUITARISTA_MSCORE_BIN` if it lives somewhere unusual.

Note that musescore.com (the score-sharing *website*) requires a paid Pro subscription to download
copyrighted scores in any format. That is unrelated to the MuseScore application, which is free. For
freely reusable scores try [OpenScore](https://musescore.org/en/openscore) (CC0),
[IMSLP](https://imslp.org) and [Mutopia](https://www.mutopiaproject.org).


## How song → tab works

`Resolve (Spotify or raw query) → Songsterr → Ultimate Guitar → Audio (upload or yt-dlp → optional Demucs
guitar stem → basic-pitch → fretting solver)`. Each tier is a `TabSource` strategy with its own timeout;
the first success wins and the UI streams the tier log over SSE. An LLM is only used inside tiers to rank
candidates, rewrite failed queries, or extract structure from messy text. It never runs as an open loop.

Canonical tab JSON: `string` 1 = highest-pitched string, `tuning` is a MIDI list for strings 1..N, durations are
fractions of a whole note. The backend serializes alphaTex for the viewer (`GET /api/v1/tabs/{id}?format=alphatex`).

## Commands
```bash
pnpm dev | build | lint | typecheck | test     # all workspaces via turbo
pnpm gen:api                                  # export FastAPI OpenAPI → packages/api-types
cd apps/api && uv run pytest -q               # backend tests
cd apps/ml  && uv run guitarista-ml probe     # check ML sidecar
```
