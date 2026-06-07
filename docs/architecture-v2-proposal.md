# Recetario — Architecture v2 (Path B — ACCEPTED)

> **Status:** ACCEPTED 2026-06-07. Path B with a **TypeScript** portable core.
> Supersedes the cloud-portable premise in the original `DESIGN.md`. This is now the
> target architecture for #27 and the re-platform. Written to survive chat compaction.
>
> **Decisions locked:**
> - Path: **B** — portable TS core + thin invoked Python ingestion helper; HTTP API dissolves.
> - Q1 Core language: **TypeScript** (shares with React + future React Native).
> - Q2 Helper transport: **one-shot CLI** to start (cold-start per import is acceptable;
>   revisit stdio JSON-RPC only if cold starts hurt).
> - Q3 Google Tasks export: **keep in the Python helper** initially (reuse the
>   battle-tested OAuth/Fernet flow; don't re-incur OAuth risk in TS yet).
> - Q4 Mobile: **reuses the TS core** — so the pure core must stay RN-compatible
>   (no Node-only APIs; fs access behind a small platform port).
> - Q5 Job/progress: **in-memory, foreground** in the desktop process (import is
>   already async/slow; job state never had sync value).

## 0. Why this exists

#27 (replace SQLite with synced flat files) forced a foundational question: once the
data is plain files in a user-chosen folder, what is the rest of the stack *for*?
Re-examining the original premises against the **current, confirmed** product vision
changed several answers.

### Confirmed constraints (the inputs that drive everything below)
- **No web UI, ever.** The app will never be a hosted service. (Kills the original
  "host the same FastAPI app, swap SQLite→Postgres" justification.)
- **Native, multi-platform, local-first:** macOS first → Windows port → eventual
  mobile app that *reads from whatever sync source* (iCloud/Dropbox/Drive folder).
- **Storage = flat files in a synced folder** (Markdown + YAML), UUID identity,
  single user. Sync is delegated entirely to the OS/3rd-party folder-sync tool.
- **Pre-delivery personal project, zero migration cost.** Free to blow things up.

### The two load-bearing realizations
1. **The localhost HTTP API's main job is mediating DB access.** Remove the DB in
   favour of local files and that job evaporates — a desktop shell can read the
   files directly (the Obsidian/Logseq model). The HTTP server stops being
   load-bearing.
2. **The flat-file storage layer is the one thing that would be built twice** if we
   write it in Python now and later move logic to a portable layer for mobile.
   That makes the core-language question a *prerequisite* of #27, not a sequel.

## 1. The Python "moat" is narrow

What is genuinely Python-locked (no good cross-platform/JS equivalent):
- **`recipe-scrapers`** — backbone of deterministic URL import (#17).
- **`yt-dlp`** — video caption extraction.

Everything else in today's backend is either small arithmetic/CRUD (trivially
portable) or has a solid TS SDK:
- Domain logic: `MacroCalculator`, `ShoppingAggregator` (groups by name+unit),
  `MealPlanner` — simple, pure, fully covered by tests.
- Flat-file read/write: `gray-matter`/`js-yaml` are TS equivalents of
  `python-frontmatter`/`PyYAML`.
- LLM extraction: Anthropic has a first-class TS SDK.
- Google Tasks export: Google has JS SDKs (but the Python OAuth flow is already
  battle-tested — see open question Q3).

**Import is plausibly a desktop-only feature**, which fits "mobile just consumes the
sync source."

## 2. Target shape

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop shell — Tauri + React/TS (macOS, then Windows)      │
│  • UI                                                         │
│  • reads/writes the synced folder DIRECTLY via Tauri fs       │
│  • invokes the Python helper on demand for import             │
├─────────────────────────────────────────────────────────────┤
│  PORTABLE TS CORE  (shared desktop + future mobile)           │
│  • domain: Recipe / MealEvent / ShoppingList (+ value objs)   │
│  • services: macros, shopping aggregation, meal planning       │
│  • storage: flat-file repos (frontmatter .md, .yaml)          │
│  • use cases / validation                                     │
│  • NO framework, NO network — pure, unit-tested (vitest)      │
├─────────────────────────────────────────────────────────────┤
│  Python ingestion helper  (desktop-only, invoked, NOT served) │
│  • recipe-scrapers, yt-dlp, html→text, (optional) LLM pass    │
│  • stdio JSON-RPC or one-shot CLI; returns a draft Recipe JSON │
│  • the TS core persists the returned draft as a .md file       │
└─────────────────────────────────────────────────────────────┘

Future mobile (React Native): reuses the PORTABLE TS CORE, reads the synced
folder, browse/plan/shop. Import is desktop-only (or a future hosted endpoint).
```

### Why stdio JSON-RPC / CLI, not a localhost HTTP server
Industry precedent for "editor/app talks to a heavy separate-process backend" is
**JSON-RPC over stdio** — the Language Server Protocol and Debug Adapter Protocol
both standardized on it precisely to avoid a listening TCP port for local IPC.
Dropping the HTTP server also removes today's real baggage: the stale-server gotcha
(Cmd+Q dance), port 8765 conflicts, the startup health-poll race, and a local TCP
attack surface.

The HTTP API isn't "removed" so much as it **dissolves**: direct file access for
data, a narrow process call for import.

## 3. Python helper contract (concrete)

A small CLI/JSON-RPC binary (still PyInstaller-frozen, but *invoked per request*,
not a long-running server). Illustrative commands:

```
import-url   { "url": "https://…" }            -> { draft: RecipeDraft } | { error }
import-video { "url": "https://youtu.be/…" }   -> { draft: RecipeDraft } | { error }
parse-html   { "url": "…", "html": "<…>" }     -> { draft: RecipeDraft } | { error }   # in-app WebView capture (#26)
version      {}                                 -> { version, capabilities }
```

`RecipeDraft` is the JSON serialization of today's `RecipeInput` (title, servings,
ingredients[], instructions_md, source_*, pre-filled macros from #35). The TS core
owns turning that draft into a persisted `.md` file. This keeps the entire #17/#26/#35
import pipeline in Python, untouched, behind a one-method-per-operation boundary.

## 4. Identity & storage (carried over from the #27 design)

- **UUID strings** as identity end-to-end (no auto-increment ints — they can't
  survive folder sync across machines). Filename short-id (first 8 chars) is
  cosmetic only.
- Layout under the chosen data dir (default `~/Documents/Recetario/`, override in
  Settings, path stored in `~/.recetario/config.json`):
  ```
  recipes/{slug}-{short8}.md          # YAML frontmatter + Markdown body
  meal-calendar/meal-calendar-YYYY-MM.yaml
  shopping-lists/shopping-{uuid}.yaml
  ```
- Atomic writes (`*.tmp` → rename); best-effort parse (missing field → safe
  default, never crash on a hand-edited file).
- Secrets stay OUT of the synced folder: keys in `~/.recetario/.env`, Google OAuth
  in `~/.recetario/`. OAuth tokens and any transient job state are **not** synced.

## 5. What gets deleted (the cruft purge)

- FastAPI app, uvicorn, all HTTP routers, the localhost server + its sidecar
  packaging, OpenAPI dump + `npm run gen:api` typed-client pipeline.
- SQLAlchemy models, Alembic, the entire relational schema + migrations.
- `owner_id` / multi-user identity seam (served the abandoned cloud path).
- `ingestion_jobs` as a DB table (job state, if still needed, is in-memory in the
  desktop process or a tiny local file — it never had sync value).
- The "cloud-portable / Postgres-swap" premise in `DESIGN.md` — explicitly retired.

## 6. How the existing tests map (regression safety)

The current **~155 tests are the spec**, not throwaway:
- Domain/service tests (macros, aggregation, meal planning, scraper→draft mapping):
  port to **vitest** in the TS core. Mechanical — same cases, same expected values.
- Ingestion tests (recipe-scrapers mapping, video, fallback, from-html): **stay in
  Python**, now testing the helper's CLI/JSON-RPC contract.
- API tests (FastAPI TestClient): mostly **dissolve**; replaced by TS storage/use-case
  tests against a temp folder.

## 7. Rough re-platform sequencing (one decisive arc, test-gated)

1. **TS core skeleton + domain + services**, ported from Python with vitest tests
   green (proves the cheap 80% moves cleanly).
2. **Flat-file storage in TS** (frontmatter/yaml repos, UUID identity, atomic write,
   best-effort parse) + tests against a temp dir.
3. **Wire the desktop UI to the TS core** (direct file access via Tauri fs plugin;
   add fs capability). Remove the HTTP client.
4. **Python helper**: reduce the backend to the ingestion CLI/JSON-RPC binary; wire
   Tauri to invoke it for import (URL/video/from-html). Keep #26 WebView capture.
5. **Settings folder picker** (Tauri dialog plugin) + `config.json` data dir.
6. **One-shot migration** from the existing SQLite → files (a Python helper command
   or a TS importer), int→UUID remap for cross-references.
7. **Delete** FastAPI/SQLAlchemy/Alembic/owner_id; rewrite `DESIGN.md`.

## 8. Open questions to resolve before building

- **Q1. Core language: TypeScript vs Rust.** TS is pragmatic (shares with React +
  future React Native; domain is trivial arithmetic; you're not Rust-fluent). Rust
  (via Tauri core, which now targets iOS/Android) is faster/maximally portable but a
  heavier lift. **Lean: TypeScript.**
- **Q2. Helper transport: one-shot CLI vs persistent stdio JSON-RPC.** CLI is simplest
  (cold-start cost per import is acceptable — import is already async/slow); stdio
  RPC avoids repeated PyInstaller cold starts. **Lean: start with one-shot CLI.**
- **Q3. Google Tasks export: keep in Python helper, or port to TS?** Keeping it in
  Python reuses the battle-tested OAuth/Fernet flow; porting to TS unifies the core
  but re-incurs OAuth risk. **Lean: keep in the Python helper initially.**
- **Q4. Where do macros/aggregation run on mobile?** Confirm mobile reuses the TS
  core (implies the core must be RN-compatible: no Node-only APIs in the pure core;
  fs access behind a small platform port).
- **Q5. Job/progress model** for import without a server: in-memory promise in the
  desktop process vs a tiny status file. **Lean: in-memory; import is foreground.**

## 9. Decision needed

Pick the path before #27 storage code is written (to avoid building the file layer
twice):
- **Path A** — do #27 in Python, keep the HTTP API. Smallest now; rebuilds storage
  for mobile later.
- **Path B (this doc)** — portable TS core + thin Python ingestion helper; HTTP API
  dissolves. Bigger now; matches the native multi-platform target; keeps the
  recipe-scrapers/yt-dlp moat and the test suite as spec.

Current lean (author + Claude): **Path B**, contingent on Q1=TypeScript.

## 10. Step-3 design decisions (ACCEPTED 2026-06-07)

Wiring `desktop/` to the TS core. Three decisions locked:

- **D1. Import/video/from-HTML ingestion + Google Tasks export: STUB OUT** during
  step 3. All data ops go through files; the Python sidecar is removed from Tauri
  boot. Import + export controls are disabled/hidden ("returns next step"); the
  Settings page (BYO keys, only consumed by the Python helper) is likewise disabled
  until step 4. Rationale: a naive hybrid is broken — import would write to the
  backend's SQLite, which the file-backed UI no longer reads, so imports would
  silently vanish. Stubbing keeps a single data path and the cleanest diff. The file
  store starts EMPTY (real data arrives via the step-6 migration); test step 3 with
  manual/hand-written recipes. The PyInstaller binary stays in-repo for step-4 reuse.
- **D2. Data dir default: `~/Documents/Recetario/data/`** (one level below the repo
  root, which itself lives at `~/Documents/Recetario` in dev — avoids scattering
  `recipes/`, `meal-calendar/`, `shopping-lists/`, `config.json` into the git repo).
  Resolved via the Tauri path API ($DOCUMENT/Recetario/data). The step-5 folder
  picker overrides it.
- **D3. Core consumption: BUILD core to `dist/`** (tsc → JS + .d.ts); package
  `exports` point at `dist` for consumers (desktop/Vite/Tauri, later Metro), while
  vitest keeps importing `src/`. CI core job gains a build step. Avoids bundler
  config to transpile a dep's `.ts` source; same shape mobile will want.

**Mechanical (no decision needed):** Tauri `FileSystem` adapter = `@tauri-apps/plugin-fs`
+ scoped capability for the data dir; composition root in `desktop/src/data/repos.ts`
(resolve data dir → build adapter → export the three repos as singletons); pages swap
`await api.GET(...)` for `await repo.method(...)`, loading/error states unchanged; the
week-view macro rollup is assembled client-side (listRange → load recipes →
MacroCalculator per-serving → MealPlanAggregator). No core logic changes in step 3.

**PR slicing (mirrors 2a/2b/2c):**
- **3a — plumbing:** core dist build + `exports` repoint + CI; `desktop` joins the
  workspace and depends on `@recetario/core`; `@tauri-apps/plugin-fs` + capability;
  `TauriFileSystem` adapter + `data/repos.ts` composition root. No page swaps yet.
- **3b — recipes:** swap RecipeList / RecipeDetail / NewRecipe to `RecipeRepository`
  + in-core `MacroCalculator`. First visible file-backed feature (.md files appear
  under the data dir).
- **3c — meals + shopping + teardown:** swap WeekCalendar + ShoppingLists to the
  core; remove the HTTP/OpenAPI client and sidecar boot; stub import/export/settings;
  drop the health badge. Ends with the localhost API no longer used for reads/writes.
