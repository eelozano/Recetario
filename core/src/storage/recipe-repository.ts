/**
 * RecipeRepository — CRUD for recipes as flat `.md` files in `<baseDir>/recipes/`.
 *
 * Depends only on the FileSystem port, so it runs against the Node adapter (tests,
 * CLI) or a Tauri adapter (desktop) unchanged. Ids are UUID strings minted on
 * create; the file's frontmatter id is authoritative, the filename cosmetic.
 */
import type { Id } from "../identity";
import { type Recipe, RecipeStatus } from "../entities/recipe";
import { atomicWrite, type FileSystem, joinPath } from "./fs";
import { newId } from "./id";
import { recipeFileName, recipeFileSuffix, RECIPES_DIR } from "./recipe-layout";
import { recipeFromMarkdown, recipeToMarkdown } from "./recipe-serialization";

export class RecipeRepository {
  constructor(
    private readonly fs: FileSystem,
    private readonly baseDir: string,
  ) {}

  private dir(): string {
    return joinPath(this.baseDir, RECIPES_DIR);
  }

  /** Persist a new recipe, minting an id and timestamps. Returns the saved record. */
  async create(input: Recipe): Promise<Recipe> {
    const now = new Date().toISOString();
    const recipe: Recipe = {
      ...input,
      id: input.id ?? newId(),
      status: input.status ?? RecipeStatus.DRAFT,
      createdAt: input.createdAt ?? now,
      updatedAt: now,
    };
    await this.write(recipe);
    return recipe;
  }

  /**
   * Overwrite an existing recipe (by id), bumping `updatedAt`. If the title (hence
   * slug) changed, the file is rewritten under the new name and the old one
   * removed, so there's never a stale duplicate.
   */
  async update(input: Recipe): Promise<Recipe> {
    if (!input.id) {
      throw new Error("RecipeRepository.update requires a recipe id");
    }
    const previousName = await this.findFileNameById(input.id);
    const recipe: Recipe = { ...input, updatedAt: new Date().toISOString() };
    await this.write(recipe);

    const currentName = recipeFileName(recipe.title, recipe.id!);
    if (previousName && previousName !== currentName) {
      await this.fs.remove(joinPath(this.dir(), previousName));
    }
    return recipe;
  }

  async getById(id: Id): Promise<Recipe | null> {
    const name = await this.findFileNameById(id);
    return name ? this.read(name) : null;
  }

  /** All recipes, skipping any file too malformed to parse into an identified record. */
  async list(): Promise<Recipe[]> {
    const out: Recipe[] = [];
    for (const name of await this.listMarkdown()) {
      const recipe = await this.read(name);
      if (recipe && recipe.id) out.push(recipe);
    }
    return out;
  }

  async delete(id: Id): Promise<void> {
    const name = await this.findFileNameById(id);
    if (name) {
      await this.fs.remove(joinPath(this.dir(), name));
    }
  }

  // --- internals ---

  private async write(recipe: Recipe): Promise<void> {
    const name = recipeFileName(recipe.title, recipe.id!);
    await atomicWrite(this.fs, joinPath(this.dir(), name), recipeToMarkdown(recipe));
  }

  private async read(name: string): Promise<Recipe | null> {
    try {
      return recipeFromMarkdown(await this.fs.readTextFile(joinPath(this.dir(), name)));
    } catch {
      return null;
    }
  }

  private async listMarkdown(): Promise<string[]> {
    if (!(await this.fs.exists(this.dir()))) return [];
    const entries = await this.fs.readDir(this.dir());
    return entries.filter((n) => n.endsWith(".md"));
  }

  private async findFileNameById(id: Id): Promise<string | null> {
    const names = await this.listMarkdown();
    // Fast path: the file's name ends with `-<short8>.md`. Verify the frontmatter
    // id in case of a short-id collision; fall back to a full scan otherwise.
    const suffix = recipeFileSuffix(id);
    const ordered = [
      ...names.filter((n) => n.endsWith(suffix)),
      ...names.filter((n) => !n.endsWith(suffix)),
    ];
    for (const name of ordered) {
      const recipe = await this.read(name);
      if (recipe?.id === id) return name;
    }
    return null;
  }
}
