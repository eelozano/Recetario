# Recetario — working notes for Claude

Local-first desktop recipe & meal-planning app. A Tauri + React/TypeScript
desktop shell on top of a portable TypeScript core (`@recetario/core`: entities,
services, flat-file storage). Data lives as flat files under
`~/Documents/Recetario/data/`, read/written through the Tauri `fs` plugin.

**Architecture v2 migration in progress** (see `docs/architecture-v2-proposal.md`).
The localhost HTTP API + PyInstaller sidecar were removed in step 3 — the app no
longer runs a backend process. The Python `backend/` still lives in the repo: it
becomes an on-demand recipe-ingestion helper (step 4) and is otherwise slated for
removal (step 7). Don't assume a running server.

## Testing workflow — rebuild the bundle after each change

The user tests changes in the **packaged `.app`**, not `tauri dev`. After
finishing a change, rebuild the bundle so they can test the real deliverable:

```bash
cd desktop
npm run tauri build   # bundle → src-tauri/target/release/bundle/{macos,dmg}/
```

`tauri build` runs `npm run build` (which builds the core to `dist/` first, then
`tsc && vite build`) before bundling — no separate step needed.

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

**Paused as of step 3.** The old Settings panel wrote an Anthropic key to
`~/.recetario/.env` for the localhost backend to read; with the backend gone the
in-app Settings page is a disabled stub. Keys return in step 5 as a local
`config.json` (data-folder picker + the API key for the on-demand import helper).
The backend, while it still runs in dev, continues to read `backend/.env` /
`~/.recetario/.env` (absolute, outside the repo/bundle, 0600).

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
