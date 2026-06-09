/** Sync-conflict detection against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  RecipeRepository,
  scanRecipeConflicts,
  resolveRecipeConflict,
  type Recipe,
} from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let repo: RecipeRepository;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-conflicts-"));
  repo = new RecipeRepository(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

const recipesDir = () => join(base, "recipes");

/** Read the raw markdown a recipe was written to, to clone it under a new name. */
async function rawOf(name: string): Promise<string> {
  const { readFile } = await import("node:fs/promises");
  return readFile(join(recipesDir(), name), "utf8");
}

async function onlyMarkdown(): Promise<string[]> {
  return (await readdir(recipesDir())).filter((n) => n.endsWith(".md"));
}

function draft(title: string, extra: Partial<Recipe> = {}): Recipe {
  return { title, ...extra };
}

describe("scanRecipeConflicts", () => {
  it("returns nothing when the recipes dir is absent or clean", async () => {
    expect(await scanRecipeConflicts(fs, base)).toEqual([]);

    await repo.create(draft("Onion Soup"));
    await repo.create(draft("Garlic Bread"));
    expect(await scanRecipeConflicts(fs, base)).toEqual([]);
  });

  it("flags two files sharing a frontmatter id (the robust signal)", async () => {
    const saved = await repo.create(draft("Onion Soup", { servings: 4 }));
    const [original] = await onlyMarkdown();
    // Simulate a sync tool dropping a conflicted copy with identical frontmatter.
    const copyName = original.replace(/\.md$/, " (Mac's conflicted copy 2026-06-08).md");
    await writeFile(join(recipesDir(), copyName), await rawOf(original));

    const groups = await scanRecipeConflicts(fs, base);
    expect(groups).toHaveLength(1);
    expect(groups[0].reason).toBe("duplicate-id");
    expect(groups[0].id).toBe(saved.id);
    expect(groups[0].files.map((f) => f.name).sort()).toEqual([copyName, original].sort());
    // The conflicted copy is recognised as suffixed; the original is not.
    const copy = groups[0].files.find((f) => f.name === copyName)!;
    expect(copy.suffixed).toBe(true);
    expect(groups[0].files.find((f) => f.name === original)!.suffixed).toBe(false);
  });

  it("orders the colliding files most-recently-updated first", async () => {
    await repo.create(draft("Stew"));
    const [original] = await onlyMarkdown();
    const olderRaw = (await rawOf(original)).replace(
      /updated_at:.*/,
      "updated_at: 2020-01-01T00:00:00.000Z",
    );
    const copyName = original.replace(/\.md$/, " (conflicted copy).md");
    await writeFile(join(recipesDir(), copyName), olderRaw);

    const [group] = await scanRecipeConflicts(fs, base);
    // Original keeps its (newer) timestamp, so it sorts ahead of the stale copy.
    expect(group.files[0].name).toBe(original);
    expect(group.files[1].name).toBe(copyName);
  });

  it("catches a suffixed copy that is too malformed to parse an id", async () => {
    await repo.create(draft("Chowder"));
    const [original] = await onlyMarkdown();
    const copyName = original.replace(/\.md$/, " (conflicted copy).md");
    await writeFile(join(recipesDir(), copyName), "not valid frontmatter at all");

    const groups = await scanRecipeConflicts(fs, base);
    expect(groups).toHaveLength(1);
    expect(groups[0].reason).toBe("conflict-suffix");
    expect(groups[0].files.map((f) => f.name).sort()).toEqual([copyName, original].sort());
  });

  it("does not flag an ordinary parenthetical that isn't a conflict marker", async () => {
    await repo.create(draft("Soup (Vegan)"));
    await repo.create(draft("Soup (Spicy)"));
    expect(await scanRecipeConflicts(fs, base)).toEqual([]);
  });
});

describe("resolveRecipeConflict", () => {
  it("removes the dropped files and leaves the kept one", async () => {
    await repo.create(draft("Onion Soup"));
    const [original] = await onlyMarkdown();
    const copyName = original.replace(/\.md$/, " (conflicted copy).md");
    await writeFile(join(recipesDir(), copyName), await rawOf(original));

    await resolveRecipeConflict(fs, base, [copyName]);

    expect(await onlyMarkdown()).toEqual([original]);
    expect(await scanRecipeConflicts(fs, base)).toEqual([]);
  });

  it("is tolerant of an already-absent file", async () => {
    await mkdir(recipesDir(), { recursive: true });
    await expect(resolveRecipeConflict(fs, base, ["ghost.md"])).resolves.toBeUndefined();
  });
});
