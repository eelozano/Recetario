/**
 * Sync-conflict detection for the recipes folder (#51, part 2).
 *
 * Folder-sync tools (Dropbox, iCloud Drive, Google Drive, Nextcloud, Syncthing)
 * don't merge — when the same recipe is edited on two machines they drop a second
 * file beside the original, e.g. `onion-soup-abc12345 (Mac's conflicted copy).md`.
 * The repository's `getById` would silently pick whichever it finds first, so the
 * losing edit would vanish from view. This module surfaces those duplicates so the
 * UI can ask the user which copy to keep.
 *
 * The robust signal is **two files carrying the same frontmatter `id`** — the id
 * is authoritative and the sync tool copies it verbatim, so it catches a conflict
 * regardless of how the vendor named the duplicate. A filename-suffix heuristic is
 * a secondary net for copies too malformed to parse an id from.
 *
 * Pure (FileSystem port only) so it runs under the Node adapter in tests and the
 * Tauri adapter in the app, unchanged.
 */
import type { Id } from "../identity";
import { type FileSystem, joinPath } from "./fs";
import { RECIPES_DIR } from "./recipe-layout";
import { recipeFromMarkdown } from "./recipe-serialization";

/** Why a set of files was flagged as conflicting. */
export type ConflictReason = "duplicate-id" | "conflict-suffix";

/** One candidate file in a conflict group. */
export interface ConflictFile {
  /** File name within the recipes dir (the authoritative id is in frontmatter). */
  name: string;
  /** Frontmatter id, if the file parsed and carried one. */
  id: Id | null;
  /** Recipe title for display, if parseable. */
  title: string | null;
  /** ISO `updatedAt` for "most recent" hinting, if present. */
  updatedAt: string | null;
  /** Whether the file name carries a sync-tool conflicted-copy marker. */
  suffixed: boolean;
}

/** Two or more files that represent the same recipe and need resolving. */
export interface ConflictGroup {
  /** Stable key: the shared id, or the stripped base name for a suffix-only match. */
  key: string;
  reason: ConflictReason;
  /** The shared frontmatter id when grouped by id; null for suffix-only groups. */
  id: Id | null;
  /** The colliding files, most-recently-updated first (best-guess canonical). */
  files: ConflictFile[];
}

/**
 * Matches the conflicted-copy markers folder-sync tools append before the
 * extension. Conservative on purpose — it requires the word "conflict" inside a
 * parenthetical (or Syncthing's `.sync-conflict-…` infix), so an ordinary recipe
 * filename never trips it.
 *   Dropbox:    "onion-soup-abc12345 (Mac's conflicted copy 2026-06-08).md"
 *   iCloud:     "onion-soup-abc12345 (conflicted copy).md"
 *   Nextcloud:  "onion-soup-abc12345 (conflicted copy 2026-06-08 120000).md"
 *   Syncthing:  "onion-soup-abc12345.sync-conflict-20260608-120000-ABCD.md"
 */
export const CONFLICT_SUFFIX_RE = /\([^()]*conflict[^()]*\)|\.sync-conflict-[0-9a-z-]+/i;

/** Strip a conflict marker (and any trailing space it leaves) from a filename. */
function strippedBaseName(name: string): string {
  return name.replace(CONFLICT_SUFFIX_RE, "").replace(/\s+(?=\.[^.]+$)/, "");
}

function dir(baseDir: string): string {
  return joinPath(baseDir, RECIPES_DIR);
}

/** Most-recent-first by `updatedAt`; files without one sort last (least canonical). */
function byUpdatedDesc(a: ConflictFile, b: ConflictFile): number {
  if (a.updatedAt && b.updatedAt) return b.updatedAt.localeCompare(a.updatedAt);
  if (a.updatedAt) return -1;
  if (b.updatedAt) return 1;
  return a.name.localeCompare(b.name);
}

/**
 * Scan the recipes folder for conflicting duplicate files. Returns one group per
 * recipe that has more than one file on disk; an empty array when all is well.
 */
export async function scanRecipeConflicts(
  fs: FileSystem,
  baseDir: string,
): Promise<ConflictGroup[]> {
  const recipesDir = dir(baseDir);
  if (!(await fs.exists(recipesDir))) return [];

  const names = (await fs.readDir(recipesDir)).filter((n) => n.endsWith(".md"));

  const files: ConflictFile[] = [];
  for (const name of names) {
    let id: Id | null = null;
    let title: string | null = null;
    let updatedAt: string | null = null;
    try {
      const recipe = recipeFromMarkdown(await fs.readTextFile(joinPath(recipesDir, name)));
      id = recipe.id ?? null;
      title = recipe.title ?? null;
      updatedAt = recipe.updatedAt ?? null;
    } catch {
      // Unparseable copy — still surfaced via the filename-suffix net below.
    }
    files.push({ name, id, title, updatedAt, suffixed: CONFLICT_SUFFIX_RE.test(name) });
  }

  const groups: ConflictGroup[] = [];
  const grouped = new Set<string>();

  // Primary: files sharing a frontmatter id are the same recipe duplicated.
  const byId = new Map<Id, ConflictFile[]>();
  for (const file of files) {
    if (!file.id) continue;
    const list = byId.get(file.id) ?? [];
    list.push(file);
    byId.set(file.id, list);
  }
  for (const [id, list] of byId) {
    if (list.length < 2) continue;
    list.sort(byUpdatedDesc);
    for (const f of list) grouped.add(f.name);
    groups.push({ key: id, reason: "duplicate-id", id, files: list });
  }

  // Secondary: copies too malformed to share a parsed id, matched by base name.
  const byBase = new Map<string, ConflictFile[]>();
  for (const file of files) {
    if (grouped.has(file.name)) continue;
    const base = strippedBaseName(file.name);
    const list = byBase.get(base) ?? [];
    list.push(file);
    byBase.set(base, list);
  }
  for (const [base, list] of byBase) {
    // Only a real conflict if a suffixed copy sits beside another file.
    if (list.length < 2 || !list.some((f) => f.suffixed)) continue;
    list.sort(byUpdatedDesc);
    groups.push({ key: base, reason: "conflict-suffix", id: null, files: list });
  }

  // Stable output order for a calm UI.
  groups.sort((a, b) => a.key.localeCompare(b.key));
  return groups;
}

/**
 * Resolve a conflict by keeping one file and removing the others. The kept file's
 * name is left as-is — the filename is cosmetic, the frontmatter id authoritative,
 * so the next edit rewrites it under the canonical `{slug}-{short8}.md` name.
 */
export async function resolveRecipeConflict(
  fs: FileSystem,
  baseDir: string,
  dropNames: string[],
): Promise<void> {
  const recipesDir = dir(baseDir);
  for (const name of dropNames) {
    await fs.remove(joinPath(recipesDir, name));
  }
}
