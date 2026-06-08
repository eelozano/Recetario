# Recetario

A **local-first desktop recipe & meal-planning app** for a single user. Import recipes from a URL
or video, record per-serving macros, plan a week of meals, and generate an aggregated shopping
list — all on your own machine, stored as plain files you own.

There is **no server and no database**. The app is a Tauri + React shell on top of a portable
TypeScript core (`@recetario/core`) that holds all the logic (macro math, grocery aggregation,
serialization) and reads/writes flat files. The same core is what a future mobile client would
reuse — not an HTTP API.

See [`DESIGN.md`](DESIGN.md) for the full architecture and the rationale behind each decision.

## How it fits together

```
┌─────────────────────────────────────────────┐     spawns on demand     ┌────────────────────────┐
│  desktop/   Tauri + React UI                  │  ───────────────────────▶│  recetario-helper       │
│  └─ @recetario/core  (entities, services,     │   (NDJSON over stdio)     │  Python import sidecar  │
│     flat-file storage)  ─▶  ~/…/Recetario/    │ ◀───────────────────────  │  recipe-scrapers/yt-dlp │
│        recipes/  meal-calendar/  shopping/    │     draft recipe JSON     │  /Claude extraction     │
└─────────────────────────────────────────────┘                           └────────────────────────┘
```

- **[`core/`](core/)** — `@recetario/core`: framework-free TypeScript entities, domain services
  (`MacroCalculator`, `ShoppingAggregator`, `MealPlanner`), and flat-file repositories behind a
  small `FileSystem` port. Pure and unit-tested with vitest; Node-/React-Native-safe.
- **[`desktop/`](desktop/README.md)** — the Tauri v2 shell + React/TypeScript UI. Injects a Tauri
  filesystem adapter into the core and reads/writes the data folder directly. No HTTP client.
- **[`backend/`](backend/README.md)** — **only** the `recetario-helper` import sidecar: a frozen
  Python CLI that turns a URL/video/captured page into a draft recipe (recipe-scrapers, yt-dlp,
  Claude) and prints JSON. It owns no storage; the TS core persists the result.

## Data

Everything lives as human-readable files under a folder you choose in Settings (default
`~/Documents/Recetario/data`, override saved in `~/.recetario/config.json`):

```
recipes/{slug}-{short8}.md            # YAML frontmatter + Markdown body
meal-calendar/meal-calendar-YYYY-MM.yaml
shopping-lists/shopping-{uuid}.yaml
```

Point the folder at Dropbox/iCloud Drive to sync across machines. Atomic writes; best-effort parse
(a hand-edited file never crashes the app).

## Quick start (development)

You need **Node 18+** and the **Rust toolchain** (for Tauri). Python is needed only to (re)build the
import helper.

```bash
cd desktop
npm install
npm run tauri dev        # builds @recetario/core, runs the UI against your data folder
```

For a **packaged double-click app** (with the frozen import helper bundled in), see
[`desktop/README.md`](desktop/README.md).

## Project status

Architecture v2 is complete: a portable TS core + flat-file storage replaced the original
FastAPI/SQLite backend; the only Python left is the on-demand import helper. Recipe import (URL,
video, and in-app browser capture) works; macros are entered by hand. See [`DESIGN.md`](DESIGN.md)
for the design and `docs/architecture-v2-proposal.md` for the migration history.

## Repository layout

```
Recetario/
  DESIGN.md          Architecture, data layout, verification strategy
  core/              @recetario/core — TS entities, services, flat-file storage (vitest)
  desktop/           Tauri + React + TypeScript shell and UI
  backend/           recetario-helper — the Python import sidecar (recipe-scrapers/yt-dlp/Claude)
  docs/              Design notes, including the Architecture v2 migration proposal
```

## Contributing

Development follows **GitHub Flow** — branch per change, PR linked to its issue, squash-merge to
`main`. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full working agreement.

## Configuration & secrets

The data folder is chosen in Settings (stored in `~/.recetario/config.json`). The import helper
reads an optional Anthropic key from `~/.recetario/.env` (`RECETARIO_ANTHROPIC_API_KEY`) — a
well-structured page imports with **no** key; the key only unlocks the LLM fallback, ingredient
structuring, and video. **Secrets are never committed** — `.env`, `*.db`, and `~/.recetario/` are
gitignored.
