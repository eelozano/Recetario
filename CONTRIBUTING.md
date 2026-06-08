# Contributing & Workflow

This is the working agreement for developing Recetario. It's tuned for a **solo,
AI-assisted** workflow on a **local-first, pre-1.0** app — light on ceremony, but with a
real review checkpoint before code lands.

## Branching model: GitHub Flow

We use **GitHub Flow**. The whole model in five rules:

1. **`main` is always shippable.** Never commit directly to `main`. Anything on `main` should
   build and pass tests.
2. **Every change starts on a short-lived branch** off the latest `main`.
3. **Open a Pull Request** for the change. The PR diff is the review checkpoint — the place to
   eyeball what was produced (especially AI-generated diffs) before it lands.
4. **Squash-merge** the PR into `main` so each logical change is one clean commit.
5. **Delete the branch** after merge.

That's it. No long-lived `develop` branch, no `release/*` or `hotfix/*` branches — those solve
team/release-cadence problems we don't have. If this ever grows into a team or gains a real
release cycle, GitHub Flow extends cleanly (add CI gates, then branch protection, then tags).

### Why a PR when it's just me?

- **Review checkpoint.** The diff view catches mistakes before they're on `main`.
- **Issue linking.** `Fixes #N` in the PR auto-closes the issue on merge.
- **A gate for later.** When CI exists, the PR is where it runs.
- **Clean history.** Squash-merge keeps `main` a readable list of logical changes.

## Branch naming

`<type>/<short-slug>` — type matches the work:

| Prefix     | For                                              | Example                          |
| ---------- | ------------------------------------------------ | -------------------------------- |
| `fix/`     | Bug fixes                                         | `fix/mf2py-pyinstaller-data`     |
| `feat/`    | New features                                      | `feat/recipe-edit-ui`            |
| `docs/`    | Docs only                                         | `docs/contributing-workflow`     |
| `chore/`   | Tooling, deps, build, housekeeping                | `chore/bump-tauri`               |
| `refactor/`| Internal restructuring, no behavior change        | `refactor/repo-owner-scope`      |

One branch = one logical change. If a change grows a second concern, branch again.

## The loop

```
1. Spot something          → file a GitHub issue (QA findings, bugs, feature ideas)
2. Pick an issue           → branch off main:  git checkout main && git pull && git checkout -b fix/thing
3. Make the change         → commit in logical steps
4. Verify                  → run tests; rebuild/boot if it touches the binary or UI
5. Open a PR               → body references the issue:  "Fixes #N"
6. Squash-merge to main    → delete the branch
7. main is shippable again
```

Issues are the backlog; branches are how they get resolved. Keep them linked so the history
explains itself.

## Commits

- Imperative subject line ("Add", "Fix", "Bundle"), ~50 chars.
- Body explains the *why*, not just the *what*, when it isn't obvious.
- End commit messages with the agent co-author trailer:

  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

Because we squash-merge, the **PR title** becomes the final commit subject on `main` — make it
a clean, standalone summary.

## Verify before merge

A change is mergeable when it's actually been exercised, not just written:

- **Core logic** (`@recetario/core`) → `cd core && npm test` (vitest, against a temp dir).
- **Import helper** → `cd backend && .venv/bin/pytest` (hermetic, offline — no live
  USDA/Anthropic/network calls).
- **The frozen import helper** (PyInstaller spec, `helper.py`, bundled deps) → rebuild with
  `desktop/scripts/build-helper.sh`, then `npm run tauri build` and exercise a real import.
  Use a **throwaway** data folder (Settings → Change folder…), never your real recipe library.
- **UI** → `cd desktop && npm run build` (typecheck) and, when it matters, `npm run tauri dev`.

## Continuous integration

Every PR runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml): the core `vitest` suite, the
import-helper `pytest` suite, and the frontend typecheck/build. The green check is a *floor*, not
the whole review — it proves
nothing imported broke, but it can't see a packaging regression, a wrong macro number, or a UI
that looks off. Treat CI as "the automatable half is handled, now verify the rest."

## Reviewing a PR

The PR is the review checkpoint — here's how to actually exercise one before merging.

**1. Read the diff first.** The GitHub "Files changed" tab is the fast pass. For a small, obvious
change (a CSS tweak, a copy fix) reading the diff *is* sufficient — no checkout needed.

**2. Check it out when you want to run it.** `gh pr checkout <number>` puts the PR's exact code in
your tree (start from a clean working tree). Then run only what the change could break:

| The PR touches…                    | Verify with                                                            |
| ---------------------------------- | ---------------------------------------------------------------------- |
| Core logic (`@recetario/core`)     | `cd core && npm test`                                                  |
| Import helper (Python)             | `cd backend && .venv/bin/pytest`                                       |
| A user-facing flow                 | + live smoke test against a **throwaway** data folder (below)          |
| PyInstaller spec / `helper.py`     | `bash desktop/scripts/build-helper.sh` + `npm run tauri build`; import |
| UI (React/TS)                      | `cd desktop && npm run build`, then `npm run tauri dev` to click it    |
| Docs only                          | just read the rendered file                                            |

**Live smoke test** (never against your real recipe library):

```bash
cd desktop && npm run tauri dev
# In the app: Settings → Change folder… → pick an empty temp dir (e.g. ~/Desktop/pr_test).
# Exercise the changed flow there; delete the folder when done. Your real data is untouched.
```

Because the app reads/writes a plain folder, a throwaway data dir *is* the whole isolation
story — no database or server to stand up.

**3. Get back cleanly.** `git checkout main && git pull`; `git branch -d <branch>` tidies up the
local PR branch after merge.

## Never commit

These stay local — they're gitignored, keep them that way:

- `backend/.env` and any real API key (Anthropic).
- `~/.recetario/` — your `config.json` and the Anthropic key in `.env`.
- `*.db`, build artifacts (`backend/dist/`, `backend/build/`, `desktop/src-tauri/binaries/`,
  `target/`), `node_modules/`, `.claude/settings.local.json`.

When staging, add files **by name** — avoid `git add -A`, which sweeps up artifacts and secrets.
The frozen import-helper binary is large and machine-specific; it's regenerated per-build, never
committed (see [`desktop/scripts/build-helper.sh`](desktop/scripts/build-helper.sh)).

## Releases (when the time comes)

Not needed yet (we're pre-1.0 with no distribution cadence). When it is: tag `main` with a
SemVer tag (`v0.2.0`), let the version in `desktop/src-tauri/tauri.conf.json` and
`backend/pyproject.toml` track it, and build the `.dmg` from that tag. No separate release
branch — the tag *is* the release marker.
