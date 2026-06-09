/**
 * Sync-conflict detection for the desktop shell (#51, part 2).
 *
 * Thin wrapper over the core's pure `scanRecipeConflicts` / `resolveRecipeConflict`
 * (storage/conflicts.ts), bound to the active data dir + Tauri filesystem adapter.
 * The React banner calls these; all the grouping logic lives — and is unit-tested
 * — in the core.
 */
import {
  resolveRecipeConflict,
  scanRecipeConflicts,
  type ConflictGroup,
} from "@recetario/core";

import { getRepos } from "./repos";

export type { ConflictGroup, ConflictFile } from "@recetario/core";

/** Conflicting recipe files in the active data folder (empty when all is well). */
export async function scanConflicts(): Promise<ConflictGroup[]> {
  const { fs, dataDir } = await getRepos();
  return scanRecipeConflicts(fs, dataDir);
}

/** Keep one copy of a conflicted recipe and delete the rest. */
export async function resolveConflict(dropNames: string[]): Promise<void> {
  const { fs, dataDir } = await getRepos();
  await resolveRecipeConflict(fs, dataDir, dropNames);
}
