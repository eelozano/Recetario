/** CustomCategoriesStore against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { CustomCategoriesStore, CUSTOM_CATEGORIES_FILE } from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let store: CustomCategoriesStore;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-categories-"));
  store = new CustomCategoriesStore(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

describe("CustomCategoriesStore", () => {
  it("returns an empty list when no file exists", async () => {
    expect(await store.load()).toEqual([]);
  });

  it("adds categories, keeping the typed label and a lowercase id", async () => {
    await store.add("Fruit");
    await store.add("  Veggies ");

    expect(await store.load()).toEqual([
      { id: "fruit", label: "Fruit" },
      { id: "veggies", label: "Veggies" },
    ]);
  });

  it("writes a flat hand-editable YAML list of labels", async () => {
    await store.add("Fruit");
    const text = await readFile(join(base, CUSTOM_CATEGORIES_FILE), "utf8");
    expect(text).toContain("- Fruit");
  });

  it("rejects blanks, duplicates, preset shadows, and reserved names", async () => {
    await store.add("Fruit");
    await expect(store.add("   ")).rejects.toThrow("name");
    await expect(store.add("fruit")).rejects.toThrow("already exists");
    await expect(store.add("Produce")).rejects.toThrow("built-in");
    await expect(store.add("__reset")).rejects.toThrow("underscore");
    expect(await store.load()).toHaveLength(1);
  });

  it("removes a category by id", async () => {
    await store.add("Fruit");
    await store.add("Veggies");
    await store.remove("fruit");
    expect(await store.load()).toEqual([{ id: "veggies", label: "Veggies" }]);
  });

  it("best-effort reads a hand-edited file, skipping junk entries", async () => {
    await writeFile(
      join(base, CUSTOM_CATEGORIES_FILE),
      ["- Fruit", "- fruit", "- produce", "- 42", "- ''", "- Veggies"].join("\n"),
    );
    expect(await store.load()).toEqual([
      { id: "fruit", label: "Fruit" },
      { id: "veggies", label: "Veggies" },
    ]);
  });
});
