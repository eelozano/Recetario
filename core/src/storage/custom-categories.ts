/**
 * User-defined shopping categories — `<baseDir>/custom-categories.yaml`, a
 * YAML list of display labels (hand-edit friendly).
 *
 * Custom categories are **local-only** extensions of the preset six (#69):
 * they appear as extra groups in the shopping list (after the presets, before
 * Other) and as choices in the row picker and overrides, but the import LLM
 * and the static map keep emitting presets — a custom category is reached via
 * the user's own picks. A category's id is its lowercased label; items and
 * overrides store the id, so deleting a category simply sends anything that
 * pointed at it back to "Other" (no migration pass needed).
 */
import { SHOPPING_CATEGORIES } from "../services/ingredient-categories";
import { atomicWrite, type FileSystem, joinPath } from "./fs";
import { dumpYaml, loadYaml } from "./yaml";

export const CUSTOM_CATEGORIES_FILE = "custom-categories.yaml";

export interface CustomCategory {
  /** Stored category value (lowercased label). */
  id: string;
  /** Label as the user typed it. */
  label: string;
}

export function customCategoryId(label: string): string {
  return label.trim().toLowerCase();
}

export class CustomCategoriesStore {
  constructor(
    private readonly fs: FileSystem,
    private readonly baseDir: string,
  ) {}

  private path(): string {
    return joinPath(this.baseDir, CUSTOM_CATEGORIES_FILE);
  }

  async load(): Promise<CustomCategory[]> {
    if (!(await this.fs.exists(this.path()))) return [];
    let data: unknown;
    try {
      data = loadYaml(await this.fs.readTextFile(this.path()));
    } catch {
      return [];
    }
    if (!Array.isArray(data)) return [];
    const out: CustomCategory[] = [];
    const seen = new Set<string>();
    for (const entry of data) {
      if (typeof entry !== "string") continue;
      const label = entry.trim();
      const id = customCategoryId(label);
      // Skip blanks, duplicates, reserved ids (leading underscore), and
      // anything shadowing a preset id.
      if (
        !id ||
        id.startsWith("_") ||
        seen.has(id) ||
        (SHOPPING_CATEGORIES as readonly string[]).includes(id)
      ) {
        continue;
      }
      seen.add(id);
      out.push({ id, label });
    }
    return out;
  }

  /** Add a category; throws with a user-facing message when the name is unusable. */
  async add(label: string): Promise<CustomCategory> {
    const trimmed = label.trim();
    const id = customCategoryId(trimmed);
    if (!id) throw new Error("Give the category a name.");
    // Leading underscores are reserved for UI sentinels (e.g. the row picker's
    // "Auto (reset)" option).
    if (id.startsWith("_")) {
      throw new Error("Category names can't start with an underscore.");
    }
    if ((SHOPPING_CATEGORIES as readonly string[]).includes(id)) {
      throw new Error(`"${trimmed}" is already a built-in category.`);
    }
    const existing = await this.load();
    if (existing.some((c) => c.id === id)) {
      throw new Error(`"${trimmed}" already exists.`);
    }
    const next = [...existing, { id, label: trimmed }];
    await this.write(next);
    return { id, label: trimmed };
  }

  /** Remove a category. Items/overrides pointing at it fall back to "Other". */
  async remove(id: string): Promise<void> {
    const existing = await this.load();
    const next = existing.filter((c) => c.id !== id);
    if (next.length === existing.length) return;
    await this.write(next);
  }

  private async write(categories: CustomCategory[]): Promise<void> {
    await atomicWrite(
      this.fs,
      this.path(),
      dumpYaml(categories.map((c) => c.label)),
    );
  }
}
