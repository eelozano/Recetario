/** RecipeRepository against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Decimal } from "decimal.js";

import { RecipeRepository, RecipeStatus, type Recipe } from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let repo: RecipeRepository;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-recipes-"));
  repo = new RecipeRepository(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

function draft(title: string, extra: Partial<Recipe> = {}): Recipe {
  return { title, ...extra };
}

describe("RecipeRepository", () => {
  it("creates a recipe, mints id + timestamps, and round-trips via getById", async () => {
    const saved = await repo.create(
      draft("Onion Soup", { servings: 2, caloriesPerServing: new Decimal("220") }),
    );

    expect(saved.id).toMatch(/[0-9a-f-]{36}/);
    expect(saved.status).toBe(RecipeStatus.DRAFT);
    expect(saved.createdAt).toBeTruthy();
    expect(saved.updatedAt).toBeTruthy();

    const loaded = await repo.getById(saved.id!);
    expect(loaded).not.toBeNull();
    expect(loaded!.title).toBe("Onion Soup");
    expect(loaded!.servings).toBe(2);
    expect(loaded!.caloriesPerServing?.toString()).toBe("220");
  });

  it("writes a {slug}-{short8}.md file and leaves no .tmp behind", async () => {
    const saved = await repo.create(draft("Onion Soup"));
    const files = await readdir(join(base, "recipes"));
    const short8 = saved.id!.replace(/-/g, "").slice(0, 8);

    expect(files).toContain(`onion-soup-${short8}.md`);
    expect(files.some((f) => f.endsWith(".tmp"))).toBe(false);
  });

  it("lists all saved recipes", async () => {
    await repo.create(draft("Apple Pie"));
    await repo.create(draft("Banana Bread"));
    const titles = (await repo.list()).map((r) => r.title).sort();
    expect(titles).toEqual(["Apple Pie", "Banana Bread"]);
  });

  it("updates content, bumps updatedAt, and renames the file on title change", async () => {
    const saved = await repo.create(draft("Old Name", { servings: 1 }));
    const short8 = saved.id!.replace(/-/g, "").slice(0, 8);

    const updated = await repo.update({
      ...saved,
      title: "New Name",
      servings: 6,
    });

    expect(updated.servings).toBe(6);
    expect(updated.updatedAt! >= saved.updatedAt!).toBe(true);

    const files = await readdir(join(base, "recipes"));
    expect(files).toEqual([`new-name-${short8}.md`]); // old file gone, no duplicate

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.title).toBe("New Name");
    expect(loaded!.servings).toBe(6);
  });

  it("deletes a recipe", async () => {
    const saved = await repo.create(draft("Temporary"));
    await repo.delete(saved.id!);
    expect(await repo.getById(saved.id!)).toBeNull();
    expect(await repo.list()).toEqual([]);
  });

  it("returns null for an unknown id and [] for an empty store", async () => {
    expect(await repo.getById("does-not-exist")).toBeNull();
    expect(await repo.list()).toEqual([]);
  });

  it("reads a hand-written file and ignores unidentifiable junk", async () => {
    const dir = join(base, "recipes");
    await mkdir(dir, { recursive: true });
    await writeFile(
      join(dir, "handmade-aaaaaaaa.md"),
      ["---", "id: 11111111-1111-1111-1111-111111111111", "title: Handmade", "---", "Mix."].join(
        "\n",
      ),
    );
    // A malformed file with no id — must be skipped, not crash list().
    await writeFile(join(dir, "broken-bbbbbbbb.md"), "not even frontmatter");

    const recipes = await repo.list();
    expect(recipes).toHaveLength(1);
    expect(recipes[0].title).toBe("Handmade");
    expect(recipes[0].instructionsMd).toBe("Mix.");
  });
});
