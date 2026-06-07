# Recetario — working notes for Claude

Local-first desktop recipe & meal-planning app. Python + FastAPI backend (Clean
Architecture / ports-and-adapters) exposed as a headless localhost JSON API,
wrapped by a Tauri + React/TypeScript desktop shell. The Python backend ships as
a PyInstaller one-file Tauri sidecar.

## Testing workflow — rebuild the bundle after each change

The user tests changes in the **packaged `.app`**, not `tauri dev`. After
finishing a change, rebuild the bundle so they can test the real deliverable:

```bash
cd desktop
bash scripts/build-sidecar.sh   # freeze backend → src-tauri/binaries/recetario-server-<triple>
npm run tauri build             # bundle → src-tauri/target/release/bundle/{macos,dmg}/
```

`build-sidecar.sh` must run first whenever backend code changes (it re-freezes
the PyInstaller binary). For frontend-only changes it's still safe to run both.

### Gotcha: rebuilding does NOT update a running app
macOS `open App.app` re-focuses an already-running instance rather than
relaunching the new binary, and closing the window doesn't quit it. After every
rebuild the user must **Cmd+Q the running app, then reopen it** — otherwise the
old sidecar (possibly missing new routes) keeps serving on port 8765. If a save
"fails" or a new endpoint 404s, suspect a stale process first
(`ps aux | grep recetario-server` and compare start time to the build time).

## Build/test commands

- Frontend typecheck + build: `cd desktop && npm run build` (`tsc && vite build`)
- Regenerate typed API client after backend schema changes:
  `cd desktop && npm run gen:api` (reads `src/api/openapi.json`)
- Backend tests: `cd backend && source .venv/bin/activate && pytest -q`
  - Tests must NOT make live external calls (USDA/Anthropic/Google). Use
    mocks/fixtures/in-memory SQLite.

## Settings / API keys (BYO keys)

Keys are stored at `~/.recetario/.env` (absolute, outside the repo/bundle, 0600).
The in-app Settings panel writes them; `GET /settings` returns only
`{configured, hint}`, never raw values. The packaged app launches with CWD `/`,
so the absolute config path is what makes keys load — a repo-relative `.env` is
invisible to the bundle.

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
