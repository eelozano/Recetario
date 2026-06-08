/**
 * Composition root for the flat-file data layer (Architecture v2, step 3).
 *
 * Resolves the data dir, builds the Tauri filesystem adapter, and constructs the
 * three core repositories once (lazily, memoized). The React pages import these
 * instead of the old localhost HTTP client — the same role the `api` singleton
 * played before.
 *
 * Data dir: resolved by the Rust side (`get_data_dir`) — the override saved in
 * `~/.recetario/config.json` if the user picked one in Settings, else the default
 * `$DOCUMENT/Recetario/data`. A custom dir lives outside the static fs capability
 * scope; Rust unlocks it at boot (and on change) via `allow_directory`, so the
 * filesystem adapter can read/write it here. Changing the dir in Settings reloads
 * the webview, which re-runs this builder against the new path.
 */
import { invoke } from "@tauri-apps/api/core";
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
  const dataDir = await invoke<string>("get_data_dir");
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
