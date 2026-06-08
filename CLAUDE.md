# Recetario — working notes for Claude

Local-first desktop recipe & meal-planning app. Tauri + React/TypeScript shell on
a portable TS core (`@recetario/core`: entities, services, flat-file storage).
Data is flat files under `~/Documents/Recetario/data/`, read/written via the Tauri
`fs` plugin. **No backend server** — the only Python left is `recetario-helper`, an
on-demand import sidecar (recipe-scrapers/yt-dlp) for URL/video/from-HTML import.

Mid-migration to this architecture (Architecture v2). Roadmap, decisions, and
remaining steps live in `docs/architecture-v2-proposal.md` — read it before
touching storage, the helper, or settings. Don't assume a running API/DB.

## Testing — always rebuild the packaged `.app`

The user tests the **bundle**, not `tauri dev`:

```bash
cd desktop
bash scripts/build-helper.sh   # re-freeze the import sidecar — ONLY if its Python changed
npm run tauri build            # → src-tauri/target/release/bundle/{macos,dmg}/
```

- `build-helper.sh` is needed only when the helper's Python (`backend/`, the
  `recetario.cli` package, or its scraping/LLM/video deps) changes; otherwise the
  staged binary is reused. `tauri build` builds the core + frontend itself.
- **After every rebuild the user must Cmd+Q the running app and reopen it** —
  `open App.app` re-focuses the old instance instead of relaunching. A "failed"
  save or stale behavior usually means they're still on the old build.

## Other commands

- Frontend typecheck/build: `cd desktop && npm run build`
- Core tests: `cd core && npm test` (vitest, Node fs adapter)
- Backend tests: `cd backend && source .venv/bin/activate && pytest -q`
  - **No live external calls** (USDA/Anthropic/Google) — mocks/fixtures/in-memory.

## API keys

Anthropic key lives at `~/.recetario/.env` (`RECETARIO_ANTHROPIC_API_KEY`),
absolute path, 0600. A well-structured page imports with **no** key; the key only
unlocks the LLM fallback, ingredient structuring, and video. The in-app Settings
page is a stub until step 5 (folder picker + `config.json`); set keys by hand.

## Security (binding)

- Secrets live OUTSIDE the repo, never committed: API keys → `backend/.env` /
  `~/.recetario/.env`; Google OAuth secret → `~/.recetario/google_client_secret.json`.
- `.env`, `*.db`, `.recetario/`, `desktop/src-tauri/binaries/` are gitignored.
  **Stage files by name — never `git add -A`.** Never print secret values.
- Don't perform the user's Google OAuth login or enter their credentials.

## Git

- Branch per feature; PR; squash-merge. **Commit/push only when asked.**
- Co-author trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- PR bodies end with: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
