# Recetario — Design Specification

Recetario is a **local-first desktop recipe & meal-planning app** for a single user, built so the
core can later be lifted into a hosted web/mobile product with minimal refactoring. The driving
constraint is **decoupling**: all business logic (macro math, grocery aggregation, recipe parsing)
and data access are isolated from the presentation layer.

## Locked technical decisions

- **Core backend:** Python + FastAPI, exposed as a *headless local JSON API* over `localhost`.
- **Desktop shell:** Tauri wrapping a web UI (React + TypeScript), talking to the API over HTTP.
- **Nutrition data:** USDA FoodData Central (FDC) is the **authoritative** source; the ingestion
  LLM matches parsed ingredient lines to FDC entries and computes portion→gram conversions.
- **LLM provider:** Anthropic Claude API (structured output / tool use) for the ingestion worker.

The central architectural bet: because the desktop GUI is *just another HTTP client* of the local
API, "going web" means hosting the same FastAPI app and swapping SQLite→Postgres (a SQLAlchemy
config change); "going mobile" means a new client against the same endpoints. **Business logic
never moves.**

---

## 1. Architectural Strategy — Clean Architecture / Ports & Adapters

Four concentric layers; the **dependency rule** points inward only (outer depends on inner, never
the reverse). Inner layers are pure Python with no framework imports.

```
            ┌─────────────────────────────────────────────┐
            │  Presentation: FastAPI routers (HTTP/JSON)    │  ← Tauri web UI is a client of this
            ├─────────────────────────────────────────────┤
            │  Infrastructure (adapters): SQLAlchemy repos, │
            │  Anthropic client, USDA FDC client, scraper,  │
            │  yt-dlp/ASR, Google Tasks connector           │
            ├─────────────────────────────────────────────┤
            │  Application (use cases) + Ports (interfaces) │
            ├─────────────────────────────────────────────┤
            │  Domain: entities, value objects, services    │  ← pure, framework-free, unit-testable
            └─────────────────────────────────────────────┘
```

- **Domain** (`recetario/domain/`): entities (`Recipe`, `RecipeIngredient`, `Ingredient`,
  `MealEvent`, `ShoppingList`), value objects (`Quantity`, `MacroProfile`), and domain services
  (`MacroCalculator`, `ShoppingAggregator`). No SQLAlchemy, no FastAPI, no network. All macro math
  and aggregation logic lives here and is tested with plain `pytest` (no DB).
- **Application** (`recetario/application/`): use-case interactors that orchestrate the domain
  (`IngestRecipeFromUrl`, `CalculateRecipeMacros`, `GenerateWeeklyShoppingList`,
  `ExportShoppingListToGoogleTasks`). Defines **ports** as `typing.Protocol`/ABCs:
  `RecipeRepository`, `NutritionProvider`, `LlmRecipeExtractor`, `TranscriptionProvider`,
  `TaskExporter`. Use cases depend only on ports.
- **Infrastructure** (`recetario/infrastructure/`): concrete adapters implementing the ports —
  SQLAlchemy repositories, `AnthropicRecipeExtractor`, `UsdaFdcClient`, `WebScraper`,
  `VideoFetcher`, `GoogleTasksConnector`. Swappable without touching domain/application.
- **Presentation** (`recetario/api/`): thin FastAPI routers + Pydantic request/response schemas.
  Wires adapters into use cases via dependency injection (FastAPI `Depends` + a small composition
  root in `deps.py`). Auto-generates OpenAPI → a typed TS client for the UI.

### Future-proofing payoff

- **Desktop → Web:** host the same FastAPI app; swap the SQLite engine URL for Postgres (SQLAlchemy
  + Alembic make this config-only). Add auth middleware + a `user_id` scope (schema already leaves
  room — see §2).
- **Desktop → Mobile:** build a React Native / native client against the identical REST contract.
- The UI never holds business rules, so all three clients stay thin.

### Repo layout

```
recetario/
  DESIGN.md
  backend/
    pyproject.toml            # deps: fastapi, sqlalchemy, alembic, pydantic, anthropic,
                              #   httpx, recipe-scrapers, yt-dlp, google-api-python-client
    alembic/                  # migrations
    src/recetario/
      domain/{entities,value_objects,services}/
      application/{ports,use_cases,dto}/
      infrastructure/{db,llm,nutrition,scraping,export,config.py}/
      api/{routers,schemas,deps.py,main.py}/
      worker/                 # async ingestion worker
    tests/{unit,integration,api}/
  desktop/                    # Tauri
    src-tauri/                # Rust shell; launches Python API as a sidecar
    src/                      # React + TS UI, generated API client
```

**Desktop packaging:** the FastAPI app is bundled as a **Tauri sidecar** (PyInstaller one-file
binary) launched on app start; the web UI talks to `http://127.0.0.1:<port>`. This keeps the "local
desktop app" UX while the backend stays a portable server.

---

## 2. Data Schema & Models (relational; SQLite now → Postgres later)

Normalized so macros link at the **ingredient line** level. Every business table carries
`created_at`/`updated_at`. A nullable `owner_id` is included now (single-user → `NULL`) so
multi-user web migration is additive, not a rewrite.

### Recipe domain

- `recipes`: `id`, `title`, `description`, `source_url`, `source_type` (`web`|`video`|`manual`),
  `servings` (yield), `rating` (nullable 1–5, low-priority feature), `status` (`draft`|`finalized`),
  `instructions_md`, timestamps.
- `recipe_steps` *(optional normalization)*: `id`, `recipe_id` FK, `position`, `text`.
- `tags`: `id`, `name` (unique). `recipe_tags`: `recipe_id` FK, `tag_id` FK (composite PK).

### Ingredient & nutrition core (the macro-tracking heart)

- `ingredients` (canonical catalog, deduped): `id`, `name`, `normalized_name` (unique),
  `usda_fdc_id` (nullable FK → `usda_foods`), `default_unit`.
- `recipe_ingredients` (the line items — **this is the ingredient-level macro link**): `id`,
  `recipe_id` FK, `ingredient_id` FK, `position`, `raw_text` (original parsed string), `quantity`
  (decimal), `unit`, `usda_fdc_id` (resolved match, nullable), `gram_weight` (portion converted to
  grams; the basis for macro math), `notes`.
- `usda_foods` (cached FDC subset): `fdc_id` (PK), `description`, `data_type`, `category`.
- `usda_food_nutrients`: `id`, `fdc_id` FK, `nutrient_id` FK, `amount` (**per 100 g basis**),
  `unit_name`.
- `nutrients` (reference): `id`, `usda_nutrient_id`, `name` (calories, protein, fat, carbs,
  sodium, …), `unit`.
- `usda_food_portions` *(for portion→gram conversion)*: `id`, `fdc_id` FK, `portion_description`,
  `gram_weight`.

**Macro derivation (computed, not stored as truth):** for a `recipe_ingredient`,
`contribution(nutrient) = (gram_weight / 100) * usda_food_nutrients.amount`. The `MacroCalculator`
domain service sums contributions per nutrient and **also returns the per-line-item breakdown**,
which the UI exposes so the user can isolate which ingredient drives fat/sodium/etc. An optional
`recipe_ingredient_nutrients` materialized cache can be added later; MVP computes on read.

### Meal calendar

- `meal_events`: `id`, `date`, `meal_type` (`breakfast`|`lunch`|`dinner`|`snack`), `recipe_id` FK,
  `servings_planned`, `notes`. A week = events filtered by date range.

### Shopping lists

- `shopping_lists`: `id`, `name`, `week_start`, `week_end`, `generated_at`, `status`
  (`draft`|`exported`).
- `shopping_list_items`: `id`, `shopping_list_id` FK, `ingredient_id` FK, `total_quantity`, `unit`,
  `checked` (bool), `external_task_id` (nullable — Google Tasks idempotency), `source_event_ids`
  (JSON of contributing `meal_events`).

### Integration / jobs

- `ingestion_jobs`: `id`, `input_url`, `input_type`, `status`
  (`queued`|`running`|`succeeded`|`failed`), `progress`, `result_recipe_id` FK (nullable), `error`,
  timestamps. Decouples the UI from long-running parse work.
- `oauth_credentials`: `id`, `provider` (`google_tasks`), encrypted `refresh_token`, `scopes`,
  `expires_at`.

**Migrations:** Alembic from day one. Use SQLAlchemy types that map cleanly to both engines
(`Numeric` for quantities, `JSON` type, timezone-aware timestamps); avoid SQLite-only constructs.

---

## 3. Ingestion & Export Interfaces

### 3a. Smart ingestion worker (LLM-powered)

Modeled as a **job** (`ingestion_jobs`) so the API returns immediately and the UI polls status. For
MVP the worker runs in-process (FastAPI `BackgroundTasks` / asyncio); the `Job` port lets it
graduate to a real queue (RQ/Celery) later without API changes.

Pipeline stages (each behind a port):

1. **Fetch / extract source text**
   - *Web URL* → `WebScraper` adapter: try `recipe-scrapers` + schema.org/JSON-LD `Recipe` first
     (deterministic, free, accurate); fall back to readability/trafilatura on raw HTML.
   - *Video URL* → `VideoFetcher` adapter: `yt-dlp` to pull existing captions/subtitles when
     available. If none, fall back to a `TranscriptionProvider` (ASR) — **note:** Claude does not
     transcribe audio, so this needs Whisper (local `faster-whisper` or a hosted ASR).
     Captions-first keeps the common case Claude-only.
2. **Structure into a draft recipe** — `LlmRecipeExtractor` (Anthropic adapter): send cleaned
   text/transcript to Claude with a **tool/JSON-schema** for structured output → `{title, servings,
   ingredient_lines:[{raw_text, quantity, unit, name}], steps[]}`.
3. **Nutrient resolution** — Claude tool-use matches each ingredient line to a USDA FDC entry
   (querying the cached `usda_foods` first, live FDC search API on miss) and computes the
   `gram_weight` portion conversion using `usda_food_portions`. Persists `usda_fdc_id` +
   `gram_weight` on each `recipe_ingredient`. Low-confidence matches are flagged for user
   confirmation.
4. **Persist as `status=draft`.** User reviews/edits/finalizes in the UI, adjusting quantities,
   swapping USDA matches, and recording real cooking adjustments.

Port shape (illustrative):

```python
class LlmRecipeExtractor(Protocol):
    def extract(self, source_text: str) -> DraftRecipe: ...
    def resolve_nutrition(self, lines: list[IngredientLine],
                          search: NutritionProvider) -> list[ResolvedIngredient]: ...
```

### 3b. Google Tasks export connector

- Port `TaskExporter.export(list: ShoppingList) -> dict[item_id, external_task_id]`.
- Adapter `GoogleTasksConnector`: OAuth2 *installed-app* flow (loopback redirect), refresh token
  stored encrypted in `oauth_credentials`. Creates a task list named e.g. `Groceries — Week of
  2026-06-08`, one task per `shopping_list_item`. Persists `external_task_id` for **idempotent
  re-sync** (update rather than duplicate). The same port admits Todoist/Reminders adapters later.

---

## 4. Implementation Roadmap (prioritized, iterative)

Each phase is independently shippable and ends with tests + a working UI slice. Build the **local
data core first**, defer LLM/cloud integrations.

- **Phase 0 — Scaffolding & architecture skeleton.** `DESIGN.md`, `backend/` layout, SQLAlchemy +
  SQLite + Alembic, FastAPI app with `/health`, OpenAPI export, composition root (`deps.py`), Tauri
  shell + minimal React UI hitting `/health`, test harness.
- **Phase 1 — Local data core (recipes & ingredients).** *(the heart; do this fully first)* Domain
  entities + SQLAlchemy repositories for `Recipe`, `Ingredient`, `RecipeIngredient`, `Tag`; CRUD use
  cases + REST endpoints; UI for manual recipe create/edit/list, tagging, rating. No nutrition/LLM
  yet.
- **Phase 2 — USDA nutrition & ingredient-level macros.** Seed/cache a USDA FDC subset; implement
  `MacroCalculator`; add **manual** ingredient→USDA linking first; endpoint + UI **breakdown view**
  showing which ingredient contributes which macros.
- **Phase 3 — Smart ingestion (LLM).** `WebScraper` → `AnthropicRecipeExtractor` →
  `ingestion_jobs` + async worker → draft→finalize flow. Then LLM-assisted USDA matching + portion
  conversion. Then video (yt-dlp captions; optional ASR fallback).
- **Phase 4 — Weekly meal calendar.** `meal_events` + use cases; week calendar UI; aggregated
  per-day/per-week macro totals reusing `MacroCalculator`.
- **Phase 5 — Aggregated shopping lists.** `ShoppingAggregator` (collect across a week, normalize
  units, dedupe by `ingredient_id`, sum); generate lists; UI check-off.
- **Phase 6 — Google Tasks export.** OAuth flow + `GoogleTasksConnector`; idempotent sync.
- **Phase 7 — Hardening & cloud-readiness.** Validate Postgres swap via the same Alembic
  migrations, add an auth seam (`owner_id` scoping), package the Tauri app with the bundled Python
  sidecar.

---

## 5. Verification Strategy

- **Domain/application:** pure `pytest` unit tests, no DB — `MacroCalculator` (per-ingredient
  breakdown, per-100g→gram math), `ShoppingAggregator` (dedup/unit normalization). Fast; proves the
  decoupling.
- **Infrastructure/repositories:** integration tests against in-memory SQLite; a CI job also runs
  them against Postgres to guarantee the migration path.
- **API:** FastAPI `TestClient` covering each router; `curl`/HTTPie smoke checks against the running
  local server.
- **Ingestion:** unit-test the parser with recorded HTML/transcript fixtures and a **mocked**
  `LlmRecipeExtractor` (no live Claude calls in tests); opt-in live tests behind an API-key flag.
- **Export:** mock the Google Tasks client; assert idempotency (re-running updates, doesn't
  duplicate).
- **End-to-end:** run `tauri dev` + the sidecar API; manually walk URL-ingest → finalize → view
  macro breakdown → schedule a week → generate shopping list → export to Google Tasks.

## Open follow-ups (non-blocking)

- Video transcription provider choice (yt-dlp captions cover most cases; pick an ASR fallback when
  needed — Claude can't transcribe audio).
- Whether to materialize `recipe_ingredient_nutrients` for performance (defer until measured).
