# Recetario

A **local-first desktop recipe & meal-planning app** for a single user. Import recipes from a URL
or video, see exactly which ingredient drives each macro, plan a week of meals, generate an
aggregated shopping list, and push it to Google Tasks — all running on your own machine against a
local database.

Recetario is built so the same core can later be lifted into a hosted web or mobile product with
minimal refactoring. The whole app is structured around **Clean Architecture / ports & adapters**:
the business logic (macro math, grocery aggregation, recipe parsing) and data access are isolated
from the presentation layer, so "going web" is mostly a config change and "going mobile" is just a
new client against the same API.

See [`DESIGN.md`](DESIGN.md) for the full design specification and the rationale behind every
decision.

## How it fits together

```
┌──────────────────────────────┐        HTTP / JSON over          ┌──────────────────────────────┐
│  desktop/   Tauri + React UI  │  ───── http://127.0.0.1:8765 ──▶ │  backend/   FastAPI core API  │
│  (thin client — no business   │                                  │  (domain + use cases + DB)    │
│   rules, just views & fetch)  │ ◀────────────────────────────    │                               │
└──────────────────────────────┘                                  └──────────────────────────────┘
```

- **[`backend/`](backend/README.md)** — the headless Python core: FastAPI JSON API, domain logic,
  SQLAlchemy/SQLite persistence, USDA nutrition, LLM ingestion, Google Tasks export. This is where
  all the business logic lives, and it is fully usable on its own (it's just an HTTP server).
- **[`desktop/`](desktop/README.md)** — the Tauri desktop shell wrapping a React + TypeScript UI.
  In a packaged build it launches the backend as a bundled **sidecar binary**, so the whole thing
  is a single double-click app with no separate terminal.

## Quick start (development)

You need **Python 3.11+**, **Node 18+**, and the **Rust toolchain** (for Tauri).

```bash
# 1. Backend — start the local API
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/alembic upgrade head            # build the SQLite schema at ~/.recetario/recetario.db
PYTHONPATH=src .venv/bin/python -m uvicorn recetario.api.main:app --port 8765

# 2. Desktop — in a second terminal, run the UI against that API
cd desktop
npm install
npm run tauri dev
```

For a **packaged double-click app** (backend frozen into the Tauri bundle), see
[`desktop/README.md`](desktop/README.md).

## Project status

All seven roadmap phases are complete: local recipe core → USDA macros → LLM ingestion (web +
video) → weekly meal calendar → aggregated shopping lists → Google Tasks export → hardening &
cloud-readiness (owner-scoping seam, opt-in Postgres validation, packaged sidecar). See the
roadmap in [`DESIGN.md` §4](DESIGN.md).

## Repository layout

```
Recetario/
  DESIGN.md          Full design spec, schema, roadmap, verification strategy
  backend/           Python FastAPI core (domain · application · infrastructure · api)
  desktop/           Tauri + React + TypeScript shell and UI
```

## Configuration & secrets

The backend is configured via `RECETARIO_*` environment variables (or a `backend/.env` file). All
have working defaults; the optional integrations need keys you supply yourself. **Secrets are never
committed** — `.env`, `*.db`, and `~/.recetario/` are gitignored. See
[`backend/README.md`](backend/README.md#configuration) for the full list.
