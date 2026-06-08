# Recetario — Design Specification

Recetario is a **local-first desktop recipe & meal-planning app** for a single user. It runs
entirely on the user's machine, stores everything as plain files the user owns, and needs no
account, server, or network connection for normal use. The driving constraint is **portability of
the core**: all business logic lives in a framework-free TypeScript package so the same logic can
later back a mobile app — by reuse, not by a network API.

> **History.** Recetario was originally built as a Python FastAPI service over `localhost` with
> SQLite, designed to "go cloud" by swapping in Postgres. That premise was retired: a hosted
> multi-user product was never the goal, and the localhost HTTP hop added a server, a database, a
> migration chain, and an OpenAPI client for zero local-app benefit. The **Architecture v2**
> migration (see `docs/architecture-v2-proposal.md`) replaced it with the design below. This
> document describes the current system, not that history.

## Locked technical decisions

- **Core:** TypeScript package `@recetario/core` — entities, domain services, and flat-file
  storage. Framework-free and Node-/React-Native-safe (filesystem access is behind a port).
- **Desktop shell:** Tauri v2 wrapping a React + TypeScript UI. It injects a filesystem adapter
  into the core and reads/writes files directly — no HTTP, no server process.
- **Storage:** human-readable flat files (Markdown + YAML) under a user-chosen folder. No database.
- **Recipe import:** a thin, frozen **Python sidecar** (`recetario-helper`) does pure extraction
  (recipe-scrapers / yt-dlp / Claude) and returns a draft as JSON; the core persists it. This is
  the only Python and the only place a network call happens.
- **Macros:** entered by the user per serving. There is no USDA/FoodData Central integration
  (the original nutrition-lookup stack was removed).

The central bet: because the core is a plain library, **"going mobile" reuses `@recetario/core`
directly** behind a platform-specific filesystem adapter — the business logic never moves and never
needs a wire protocol.

---

## 1. Architecture

```
┌───────────────────────────────────────────────┐   spawn + NDJSON/stdio   ┌────────────────────────┐
│ desktop/  Tauri shell + React/TS UI            │ ────────────────────────▶│ recetario-helper        │
│   src/data/repos.ts   composition root         │   from-url/-video/-html  │ (frozen Python sidecar) │
│   src/data/tauri-fs.ts  FileSystem adapter     │ ◀──────────────────────  │ recipe-scrapers/yt-dlp  │
│        │ injects                               │     draft recipe JSON    │ /Claude — pure extract  │
│        ▼                                        │                          └────────────────────────┘
│   @recetario/core                              │
│     entities · services · flat-file repos      │ ──▶ files under the data dir
└───────────────────────────────────────────────┘
```

**`@recetario/core`** (`core/`) — three layers, all pure TypeScript:
- *entities* — `Recipe`, `RecipeIngredient`, `Ingredient`, `Tag`, `MealEvent`, `ShoppingList`,
  with UUID string identity and `decimal.js` quantities.
- *services* — `MacroCalculator` (per-serving totals from manual macros), `MealPlanner` (day/week
  rollups), `ShoppingAggregator` (dedupe + sum ingredients across a planned week).
- *storage* — one repository per aggregate (`RecipeRepository`, `MealEventRepository`,
  `ShoppingListRepository`) writing files through a small `FileSystem` **port**. The port has two
  adapters: Node `fs` (for vitest) and `@tauri-apps/plugin-fs` (in the app). The core never imports
  `node:fs`, so it stays React-Native-safe.

**Desktop shell** (`desktop/`) — Tauri v2 + React. `src/data/repos.ts` is the composition root:
it asks Rust for the active data dir, builds the Tauri filesystem adapter, and constructs the three
repositories as session singletons. Pages call `repo.method(...)`; week/day macro rollups are
assembled client-side (load recipes → `MacroCalculator` → `MealPlanner`).

**Import helper** (`backend/`) — the lone Python sidecar; see §3.

---

## 2. Identity & storage

- **UUID strings** end-to-end. Auto-increment ints can't survive folder sync across machines; a
  filename short-id (first 8 chars of the UUID) is cosmetic only.
- Layout under the chosen data dir (default `~/Documents/Recetario/data`; the chosen path is saved
  in `~/.recetario/config.json`):
  ```
  recipes/{slug}-{short8}.md            # YAML frontmatter + Markdown instructions body
  meal-calendar/meal-calendar-YYYY-MM.yaml
  shopping-lists/shopping-{uuid}.yaml
  ```
- **Atomic writes** (`*.tmp` → rename) and **best-effort parse**: a missing or malformed field
  falls back to a safe default; a hand-edited file never crashes the app.
- **Sync-friendly.** The data dir can be a Dropbox/iCloud folder. Secrets stay *out* of it — the
  import key lives in `~/.recetario/.env`, never in the synced data.
- **Settings.** A folder picker (Tauri dialog) changes the data dir; a custom dir outside the
  static filesystem capability scope is unlocked at runtime on the Rust side
  (`app.fs_scope().allow_directory(dir, true)`), persisted, and re-allowed at the next launch.

---

## 3. Import helper contract

A PyInstaller-frozen binary spawned by the desktop app and kept warm (`serve` mode: newline-
delimited JSON over stdin/stdout; exits on EOF at app quit). It does **pure extraction** — no
storage, no database, no macros.

```
from-url    { "url": "https://…" }           -> { recipe: <draft> } | { error }
from-video  { "url": "https://youtu.be/…" }   -> { recipe: <draft> } | { error }
from-html   { "url": "…", "html": "<…>" }     -> { recipe: <draft> } | { error }   # in-app capture
```

- *Web URL* → recipe-scrapers + schema.org/JSON-LD first (deterministic, no key); falls back to a
  Claude extraction pass on the page text when a page has no parseable schema.
- *Video URL* → yt-dlp pulls existing captions/subtitles; Claude structures the transcript.
- *from-html* → the in-app browser (for bot-protected pages) captures rendered HTML and sends it on
  the same request; same scrape-then-LLM path.

The draft is the JSON form of the core's `Recipe` input (title, servings, ingredient lines,
instructions, source). A well-structured page imports with **no** API key; the Anthropic key
(`~/.recetario/.env`) only unlocks the LLM fallback, ingredient structuring, and video. The TS core
turns the draft into a persisted `.md` file as a **draft** the user reviews and finalizes.

---

## 4. What the system deliberately does *not* have

- **No server / HTTP API.** The UI calls the core in-process. (Removed: FastAPI, uvicorn, the
  localhost API, OpenAPI + the generated typed client.)
- **No database or migrations.** Files are the source of truth. (Removed: SQLAlchemy, Alembic, the
  relational schema.)
- **No multi-user seam.** Single user, single machine. (Removed: the `owner_id` scoping.)
- **No nutrition database.** Macros are manual. (Removed: USDA FoodData Central client + seeder.)
- **No background job store.** Import is a foreground async call in the desktop process; there is no
  `ingestion_jobs` table.
- **No checklist export.** Google Tasks export was removed; a future export can start clean.

---

## 5. Verification strategy

- **Core** (`core/`, vitest): domain services (macro math, aggregation, meal planning) and the
  flat-file repositories against a temp directory via the Node adapter. These are the spec and the
  regression net.
- **Import helper** (`backend/`, pytest): the CLI/JSON contract, the `serve` loop, and the
  scraper/LLM/transcript → draft mappings, using recorded HTML/transcript fixtures and a mocked
  Anthropic client. **No live external calls.**
- **Desktop**: TypeScript typecheck + Vite build; manual smoke-test in the packaged `.app`
  (add/import/finalize a recipe, plan a week, generate a shopping list, switch the data folder).

---

## 6. Future directions (non-blocking)

- **Mobile** reuses `@recetario/core` behind a React-Native filesystem adapter — no API to build.
- **Import speed**: the helper is kept warm to amortize the Python/recipe-scrapers cold start;
  further tuning is tracked separately.
- **Checklist export** to some destination (print, share sheet, a task app) — design TBD.
