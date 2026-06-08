# Recetario — Import helper (`recetario-helper`)

The **only** Python left in Recetario. It's an on-demand sidecar that turns a recipe URL, a video
link, or a captured page into a structured *draft recipe* and prints it as JSON. It does **pure
extraction** — no storage, no database, no macros lookup. The TypeScript core (`@recetario/core`)
owns persistence; this binary just parses.

The desktop app spawns it once and keeps it warm, exchanging newline-delimited JSON over
stdin/stdout (see `serve` below). Everything else from the old FastAPI backend — the HTTP API,
SQLAlchemy/SQLite, USDA nutrition, Google Tasks export, the `owner_id` seam — was removed in the
Architecture v2 migration.

## What it does

```
src/recetario/
  cli/import_helper.py            The CLI: from-url · from-video · from-html · serve
  infrastructure/
    scraping/recipe_scraper.py    recipe-scrapers / JSON-LD + microdata, httpx fetch
    video/transcript_fetcher.py   yt-dlp caption/subtitle fetch + parse
    llm/recipe_extractor.py       Anthropic structured extraction / ingredient structuring
    config.py                     Anthropic key + model, read from env / ~/.recetario/.env
  application/dto, application/ports, domain/entities
                                  the draft-recipe shapes the pipeline maps onto (RecipeInput …)
helper.py                         frozen entry point (PyInstaller analyses this)
packaging/recetario-helper.spec   one-file PyInstaller spec
```

A well-structured page imports with **no** API key (the deterministic recipe-scrapers pass). The
Anthropic key only unlocks the LLM fallback (pages with no parseable schema), ingredient
structuring, and video transcripts.

## CLI

```
from-url    { "url": "https://…" }                 -> { recipe: <draft> } | { error }
from-video  { "url": "https://youtu.be/…" }         -> { recipe: <draft> } | { error }
from-html   { "url": "…", "html": "<…>" }           -> { recipe: <draft> } | { error }
serve       (NDJSON requests on stdin → responses)  long-lived; exits on EOF (app quit)
```

In `serve` mode each stdin line is a JSON request `{ "id", "command", ...params }` and each stdout
line is `{ "id", "ok", "recipe" | "error" }`. A bad request never kills the loop — the process
stays warm for the next import.

## Setup

Requires **Python 3.11+**.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'        # helper + test deps
```

## Configuration

Only the Anthropic credentials, read from `RECETARIO_*` env vars or `~/.recetario/.env`
(`src/recetario/infrastructure/config.py`):

| Variable                      | Default             | Purpose                                                       |
| ----------------------------- | ------------------- | ------------------------------------------------------------- |
| `RECETARIO_ANTHROPIC_API_KEY` | _unset_             | Enables the LLM pass. Absent → deterministic scraper only.    |
| `RECETARIO_ANTHROPIC_MODEL`   | `claude-sonnet-4-6` | Model tier for extraction/structuring.                        |

> **Secrets are never committed.** `.env` and `~/.recetario/` are gitignored; set the key by hand in
> `~/.recetario/.env` (0600).

## Testing

```bash
.venv/bin/pytest                          # hermetic — no live USDA/Anthropic/network calls
```

The suite mocks the Anthropic client and uses recorded HTML/transcript fixtures:

- `tests/unit/test_import_helper.py` — the CLI/JSON contract (payload shape, the `serve` loop,
  no-key error paths).
- `tests/unit/test_scraper_mapping.py` — recipe-scrapers → draft mapping (deterministic).
- `tests/unit/test_llm_extractor_mapping.py` — Anthropic structured output → draft.
- `tests/unit/test_transcript_fetcher.py` — yt-dlp caption parsing.

## Packaging (sidecar binary)

The helper is frozen into a single-file binary with PyInstaller and staged for Tauri:

```bash
.venv/bin/pip install -e '.[build]'       # adds pyinstaller
# Usually invoked via desktop/scripts/build-helper.sh, which stages the output for Tauri:
.venv/bin/pyinstaller packaging/recetario-helper.spec
```

The spec bundles recipe-scrapers, mf2py, anthropic, and yt-dlp. See
[`desktop/README.md`](../desktop/README.md) for how Tauri spawns the staged binary, and the project
[`CLAUDE.md`](../CLAUDE.md) for when a rebuild (`build-helper.sh`) is actually needed.

## Dependency extras

- `.[dev]` — pytest.
- `.[build]` — pyinstaller (build-time only; not needed at runtime).
