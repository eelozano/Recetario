/**
 * Composition root for the flat-file data layer (Architecture v2, step 3).
 *
 * Resolves the data dir, builds the Tauri filesystem adapter, and constructs the
 * three core repositories once (lazily, memoized). The React pages import these
 * instead of the old localhost HTTP client — the same role the `api` singleton
 * played before.
 *
 * Data dir: `$DOCUMENT/Recetario/data` for now. In dev this repo lives at
 * `~/Documents/Recetario`, so the store lands at `./data` (gitignored). The
 * step-5 settings folder picker will make this configurable (and will need to
 * extend the fs capability scope at runtime).
 */
import { documentDir, join } from "@tauri-apps/api/path";
import {
  MealEventRepository,
  RecipeRepository,
  ShoppingListRepository,
} from "@recetario/core";

import { TauriFileSystem } from "./tauri-fs";

export interface Repos {
  /** Absolute path of the active data dir (shown in settings/diagnostics). */
  dataDir: string;
  recipes: RecipeRepository;
  meals: MealEventRepository;
  shopping: ShoppingListRepository;
}

let cached: Promise<Repos> | null = null;

async function build(): Promise<Repos> {
  const dataDir = await join(await documentDir(), "Recetario", "data");
  const fs = new TauriFileSystem();
  // Ensure the data dir exists so the user can find it even before the first
  // save; the repositories also create their own subdirs on write.
  await fs.mkdir(dataDir);
  return {
    dataDir,
    recipes: new RecipeRepository(fs, dataDir),
    meals: new MealEventRepository(fs, dataDir),
    shopping: new ShoppingListRepository(fs, dataDir),
  };
}

/** Lazily build and memoize the repositories for the session. */
export function getRepos(): Promise<Repos> {
  return (cached ??= build());
}
