# Recetario — Backend (core API)

The headless Python core of Recetario: a **FastAPI JSON API** over `localhost` that owns all the
business logic and data. The desktop UI (and any future web/mobile client) is just an HTTP client
of this server.

Built with **Clean Architecture / ports & adapters** — the dependency rule points inward only, so
the domain logic has no idea FastAPI or SQLAlchemy exist.

## Architecture

```
api/             Presentation: thin FastAPI routers + Pydantic schemas + composition root (deps.py)
  └─ depends on
application/     Use cases (interactors) + ports (Protocol interfaces) + DTOs
  └─ depends on
domain/          Pure entities, value objects, services (MacroCalculator, ShoppingAggregator).
                   No framework imports. 100% unit-testable with plain pytest.

infrastructure/  Adapters implementing the ports — swappable without touching the inner layers:
  db/              SQLAlchemy models + repositories (owner-scoped)
  nutrition/       USDA FoodData Central client + seeder
  llm/             Anthropic recipe extractor (structured output / tool use)
  scraping/        recipe-scrapers / JSON-LD web adapter
  video/           yt-dlp caption/transcript fetcher
  export/          Google Tasks connector
  security/        Fernet token encryption for stored OAuth credentials
```

The **composition root** lives in `api/deps.py`: it wires concrete adapters into use cases via
FastAPI `Depends`, reading factories off `app.state`. Tests override those factories to stay
hermetic and offline.

## Setup

Requires **Python 3.11+**.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'        # app + test deps
.venv/bin/alembic upgrade head           # build the schema (default: ~/.recetario/recetario.db)
```

## Running the API

```bash
# From backend/ — note PYTHONPATH=src for bare runs (the package lives under src/)
PYTHONPATH=src .venv/bin/python -m uvicorn recetario.api.main:app --reload --port 8765
```

- Health check: `curl http://127.0.0.1:8765/health` → `{"status":"ok"}`
- Interactive API docs: <http://127.0.0.1:8765/docs>
- OpenAPI schema: <http://127.0.0.1:8765/openapi.json> (the desktop client is generated from this)

There is also `server.py`, the **sidecar entry point** used by the packaged desktop app: it runs
`alembic upgrade head` itself and then starts uvicorn. It is what gets frozen into the single-file
binary (see [Packaging](#packaging)).

## API surface

| Router                | Responsibility                                                      |
| --------------------- | ------------------------------------------------------------------ |
| `health`              | Liveness probe                                                     |
| `recipes`             | CRUD for recipes, ingredients, tags; draft→finalize flow          |
| `nutrition`           | USDA lookups + per-ingredient macro breakdown for a recipe        |
| `ingestion`           | Import-from-URL/video jobs (async worker) + status polling        |
| `meals`               | Weekly meal calendar (`meal_events`) + aggregated macro totals    |
| `shopping`            | Generate aggregated shopping lists from a week; check-off items   |
| `integrations`        | Google Tasks OAuth + idempotent shopping-list export             |

## Configuration

Settings are read from `RECETARIO_*` environment variables or a `backend/.env` file
(`src/recetario/infrastructure/config.py`). All have working defaults.

| Variable                              | Default                                        | Purpose                                                                 |
| ------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------- |
| `RECETARIO_DATABASE_URL`              | `sqlite:///~/.recetario/recetario.db`          | **The single knob that switches SQLite ↔ Postgres.**                    |
| `RECETARIO_API_HOST` / `_API_PORT`    | `127.0.0.1` / `8765`                           | Where the API binds.                                                    |
| `RECETARIO_FDC_API_KEY`               | _unset_                                        | USDA FoodData Central key — needed only for the nutrition seeder/lookups. |
| `RECETARIO_ANTHROPIC_API_KEY`         | _unset_                                        | Enables the LLM ingestion pass. Absent → deterministic scraper only.    |
| `RECETARIO_ANTHROPIC_MODEL`           | `claude-sonnet-4-6`                            | Model tier for ingestion.                                               |
| `RECETARIO_GOOGLE_CLIENT_SECRET_FILE` | `~/.recetario/google_client_secret.json`       | OAuth "Desktop app" credential for Google Tasks export.                 |
| `RECETARIO_TOKEN_KEY_FILE`            | `~/.recetario/token.key`                       | Local Fernet key encrypting stored OAuth tokens at rest.                |

> **Secrets are never committed.** `.env`, `*.db`, and `~/.recetario/` are gitignored. API keys
> live in `backend/.env`; the Google client secret lives under `~/.recetario/` (outside the repo).

## Database & migrations

- **Alembic from day one.** Migrations are versioned in `alembic/versions/`; `alembic upgrade head`
  builds the current schema (head revision `f2a6d5e8c1b4`).
- Schema is designed to map cleanly to both SQLite and Postgres — the SQLite→Postgres switch is
  config-only (`RECETARIO_DATABASE_URL`).
- A nullable/defaulted `owner_id` scopes every business table, so multi-user is an **additive**
  change later (the repositories already isolate by owner; only `api/deps.get_owner_id` needs to
  change).

## Testing

```bash
.venv/bin/pytest                          # default: hermetic, in-memory SQLite, no network
```

The suite is **offline by default** — LLM/USDA/Google calls are mocked, and the DB is in-memory
SQLite. Layers:

- `tests/unit/` — pure domain/application logic (macro math, aggregation), no DB.
- `tests/integration/` — repositories against a real engine.
- `tests/api/` — FastAPI `TestClient` per router.

### Opt-in Postgres validation

The same tests can run against Postgres to prove the swap, without imposing Postgres on everyday
runs:

```bash
# Throwaway Postgres
docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# Point the suite at it — the same tests now exercise Postgres
RECETARIO_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
    .venv/bin/pytest
```

`tests/integration/test_postgres_migrations.py` additionally runs `alembic upgrade head` from an
empty database and asserts the full schema — validating the migration chain itself, not just
`create_all`. It skips unless `RECETARIO_TEST_DATABASE_URL` is set.

## Packaging (sidecar binary)

For the desktop app, the backend is frozen into a single-file binary with PyInstaller:

```bash
.venv/bin/pip install -e '.[build]'       # adds pyinstaller
# Usually invoked via desktop/scripts/build-sidecar.sh, which stages the output for Tauri:
.venv/bin/pyinstaller packaging/recetario-server.spec --noconfirm --distpath dist --workpath build/pyi
```

The spec bundles the `alembic/` migrations and the `yt_dlp` dependency (so video-URL ingestion
works in the packaged app). The frozen binary self-migrates on launch. See
[`desktop/README.md`](../desktop/README.md) for how Tauri spawns it.

## Dependency extras

- `.[dev]` — pytest + `psycopg[binary]` (the Postgres driver, used by the opt-in validation path).
- `.[build]` — pyinstaller (build-time only; not needed at runtime).
