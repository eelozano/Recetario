/**
 * User category overrides — `<baseDir>/category-overrides.yaml`, a flat
 * normalizedName → category YAML map (hand-edit friendly, like everything else
 * in the data dir).
 *
 * Written when the user recategorizes a shopping list item; consulted at list
 * generation and manual-add time, where it outranks both the import LLM's
 * category and the static map — the user's "I buy tortillas in the bakery
 * aisle" knowledge beats any guess. Best-effort read: unknown categories and
 * empty names are dropped, a garbled file reads as no overrides.
 */
import { atomicWrite, type FileSystem, joinPath } from "./fs";
import { normalizeIngredientName } from "./normalize";
import { dumpYaml, loadYaml } from "./yaml";

export const CATEGORY_OVERRIDES_FILE = "category-overrides.yaml";

/**
 * Override values are category ids: one of the preset six or a user-defined
 * custom category (see ./custom-categories). Ids are lowercase by construction,
 * so values are folded on read/write; anything unregistered simply displays
 * under "Other" rather than being rejected here — the store can't know the
 * registry, and dropping data on read would make a deleted custom category
 * destroy the overrides that pointed at it.
 */
function asCategoryId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const id = value.trim().toLowerCase();
  return id || null;
}

export class CategoryOverridesStore {
  constructor(
    private readonly fs: FileSystem,
    private readonly baseDir: string,
  ) {}

  private path(): string {
    return joinPath(this.baseDir, CATEGORY_OVERRIDES_FILE);
  }

  async load(): Promise<Map<string, string>> {
    const out = new Map<string, string>();
    if (!(await this.fs.exists(this.path()))) return out;
    let data: unknown;
    try {
      data = loadYaml(await this.fs.readTextFile(this.path()));
    } catch {
      return out;
    }
    if (typeof data !== "object" || data === null) return out;
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const name = normalizeIngredientName(key);
      const category = asCategoryId(value);
      if (name && category !== null) out.set(name, category);
    }
    return out;
  }

  /** Upsert one override (keyed by the normalized ingredient name). */
  async set(ingredientName: string, category: string): Promise<void> {
    const name = normalizeIngredientName(ingredientName);
    const id = asCategoryId(category);
    if (!name || id === null) return;
    const map = await this.load();
    map.set(name, id);
    await this.write(map);
  }

  /** Forget the preference for one ingredient (no-op if none is saved). */
  async remove(ingredientName: string): Promise<void> {
    const name = normalizeIngredientName(ingredientName);
    if (!name) return;
    const map = await this.load();
    if (!map.delete(name)) return;
    await this.write(map);
  }

  /** Forget every saved preference. */
  async clear(): Promise<void> {
    await this.write(new Map());
  }

  private async write(map: Map<string, string>): Promise<void> {
    const data: Record<string, string> = {};
    for (const key of [...map.keys()].sort()) data[key] = map.get(key)!;
    await atomicWrite(this.fs, this.path(), dumpYaml(data));
  }
}
