# Recetario — working notes for Claude

Local-first desktop recipe & meal-planning app. A Tauri + React/TypeScript
desktop shell on top of a portable TypeScript core (`@recetario/core`: entities,
services, flat-file storage). Data lives as flat files under
`~/Documents/Recetario/data/`, read/written through the Tauri `fs` plugin.

**Architecture v2 migration in progress** (see `docs/architecture-v2-proposal.md`).
The localhost HTTP API + long-running PyInstaller server were removed in step 3 —
the app no longer runs a backend process. Recipe **import** (step 4) is the one
exception: it shells out to `recetario-helper`, a frozen Python CLI bundled as an
on-demand Tauri sidecar that does pure extraction (URL/video/from-HTML → JSON; the
TS core persists). The rest of `backend/` is slated for removal in step 7. Don't
assume a running server.

## Testing workflow — rebuild the bundle after each change

The user tests changes in the **packaged `.app`**, not `tauri dev`. After
finishing a change, rebuild the bundle so they can test the real deliverable:

```bash
cd desktop
bash scripts/build-helper.sh   # freeze import CLI → src-tauri/binaries/recetario-helper-<triple>
npm run tauri build            # bundle → src-tauri/target/release/bundle/{macos,dmg}/
```

`build-helper.sh` must run whenever the helper's Python (`backend/`, the
`recetario.cli` package, or its scraping/LLM/video deps) changes — `externalBin`
won't bundle, and `cargo`/`tauri build` will fail, until the staged binary exists.
For frontend-only changes you can skip it if the binary is already staged.
`tauri build` runs `npm run build` (which builds the core to `dist/` first, then
`tsc && vite build`) before bundling.

### Gotcha: rebuilding does NOT update a running app
macOS `open App.app` re-focuses an already-running instance rather than
relaunching the new binary, and closing the window doesn't quit it. After every
rebuild the user must **Cmd+Q the running app, then reopen it** — otherwise
they're still testing the old build.

## Build/test commands

- Frontend typecheck + build: `cd desktop && npm run build` (builds core, `tsc && vite build`)
- Core tests: `cd core && npm test` (vitest; uses the Node fs adapter)
- Backend tests: `cd backend && source .venv/bin/activate && pytest -q`
  - Tests must NOT make live external calls (USDA/Anthropic/Google). Use
    mocks/fixtures/in-memory SQLite.

## Settings / API keys (BYO keys)

**Settings UI paused as of step 3** (returns in step 5 as a local `config.json` —
data-folder picker + the import key). The in-app Settings page is a disabled stub.

The import helper still needs the Anthropic key: it reads `~/.recetario/.env`
(absolute, 0600, outside the repo/bundle) via the shared Settings loader, same as
the old backend. A well-structured page imports with **no** key (deterministic
recipe-scrapers); the key only unlocks the LLM fallback, ingredient structuring,
and video transcripts. Until the step-5 picker lands, set it by hand in that file.

## Security constraints (binding)

- Secrets live OUTSIDE the repo and must NEVER be committed:
  - FDC + Anthropic keys → `backend/.env` and/or `~/.recetario/.env`
  - Google OAuth client secret → `~/.recetario/google_client_secret.json`
- `.env`, `*.db`, `.recetario/` are gitignored. When staging, add files by name
  (avoid `git add -A`). Never print secret values.
- Do not perform the user's Google OAuth login or enter their credentials.

## Git

- Branch per feature; open a PR (squash-merge). Commit/push only when asked.
- Co-author trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
