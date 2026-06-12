/** CategoryOverridesStore against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { CategoryOverridesStore, CATEGORY_OVERRIDES_FILE } from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let store: CategoryOverridesStore;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-overrides-"));
  store = new CategoryOverridesStore(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

describe("CategoryOverridesStore", () => {
  it("returns an empty map when no file exists", async () => {
    expect((await store.load()).size).toBe(0);
  });

  it("round-trips overrides, normalizing the key", async () => {
    await store.set("  Tortillas ", "pantry");
    await store.set("gochujang", "other");

    const map = await store.load();
    expect(map.get("tortillas")).toBe("pantry");
    expect(map.get("gochujang")).toBe("other");
    expect(map.size).toBe(2);
  });

  it("updates an existing override in place", async () => {
    await store.set("tortillas", "pantry");
    await store.set("tortillas", "frozen");

    const map = await store.load();
    expect(map.get("tortillas")).toBe("frozen");
    expect(map.size).toBe(1);
  });

  it("writes a flat hand-editable YAML map", async () => {
    await store.set("milk", "dairy");
    const text = await readFile(join(base, CATEGORY_OVERRIDES_FILE), "utf8");
    expect(text).toContain("milk: dairy");
  });

  it("keeps custom category ids, folding them to lowercase", async () => {
    // Values aren't restricted to the presets: custom categories are user
    // strings, and an unregistered one just displays under Other.
    await writeFile(
      join(base, CATEGORY_OVERRIDES_FILE),
      "apple: Fruit\nmilk: dairy\nbroken: 42\n",
    );
    const map = await store.load();
    expect(map.get("apple")).toBe("fruit");
    expect(map.get("milk")).toBe("dairy");
    expect(map.get("broken")).toBeUndefined(); // non-string value dropped
  });

  it("survives a garbled file", async () => {
    await writeFile(join(base, CATEGORY_OVERRIDES_FILE), ": : not yaml : :");
    expect((await store.load()).size).toBe(0);
  });

  it("removes a single override", async () => {
    await store.set("tortillas", "pantry");
    await store.set("milk", "dairy");
    await store.remove("Tortillas"); // normalized like set

    const map = await store.load();
    expect(map.has("tortillas")).toBe(false);
    expect(map.get("milk")).toBe("dairy");
  });

  it("clears all overrides", async () => {
    await store.set("tortillas", "pantry");
    await store.set("milk", "dairy");
    await store.clear();
    expect((await store.load()).size).toBe(0);
  });
});
