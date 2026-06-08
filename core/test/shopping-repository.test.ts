/** ShoppingListRepository against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Decimal } from "decimal.js";

import { ShoppingListRepository, type ShoppingList } from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let repo: ShoppingListRepository;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-shopping-"));
  repo = new ShoppingListRepository(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

function sampleList(): ShoppingList {
  return {
    name: "Groceries — Week of 2026-06-08",
    weekStart: "2026-06-08",
    weekEnd: "2026-06-14",
    items: [
      {
        ingredientName: "Onion",
        unit: "pc",
        totalQuantity: new Decimal("5"),
        sourceEventIds: ["evt-1", "evt-2"],
      },
      { ingredientName: "Salt" }, // quantity-less
    ],
  };
}

describe("ShoppingListRepository", () => {
  it("creates a list, mints id + timestamps, and round-trips via getById", async () => {
    const saved = await repo.create(sampleList());

    expect(saved.id).toMatch(/[0-9a-f-]{36}/);
    expect(saved.generatedAt).toBeTruthy();

    const files = await readdir(join(base, "shopping-lists"));
    expect(files).toEqual([`shopping-${saved.id}.yaml`]);

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.name).toBe("Groceries — Week of 2026-06-08");
    expect(loaded!.weekStart).toBe("2026-06-08");
    expect(loaded!.items).toHaveLength(2);
    expect(loaded!.items![0].totalQuantity?.toString()).toBe("5");
    expect(loaded!.items![0].sourceEventIds).toEqual(["evt-1", "evt-2"]);
    expect(loaded!.items![0].checked).toBe(false);
    expect(loaded!.items![1].ingredientName).toBe("Salt");
    expect(loaded!.items![1].totalQuantity).toBeUndefined();
  });

  it("lists all saved lists", async () => {
    await repo.create(sampleList());
    await repo.create({ ...sampleList(), name: "Second list" });
    const names = (await repo.list()).map((l) => l.name).sort();
    expect(names).toEqual(["Groceries — Week of 2026-06-08", "Second list"]);
  });

  it("persists check-off state on update", async () => {
    const saved = await repo.create(sampleList());
    const items = saved.items!.map((it, i) => (i === 0 ? { ...it, checked: true } : it));
    await repo.update({ ...saved, items });

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.items![0].checked).toBe(true);
    expect(loaded!.items![1].checked).toBe(false);
  });

  it("deletes a list", async () => {
    const saved = await repo.create(sampleList());
    await repo.delete(saved.id!);
    expect(await repo.getById(saved.id!)).toBeNull();
    expect(await repo.list()).toEqual([]);
  });

  it("returns null for an unknown id and [] for an empty store", async () => {
    expect(await repo.getById("nope")).toBeNull();
    expect(await repo.list()).toEqual([]);
  });

  it("best-effort reads a hand-written file, skipping nameless items", async () => {
    const dir = join(base, "shopping-lists");
    await mkdir(dir, { recursive: true });
    await writeFile(
      join(dir, "shopping-handmade.yaml"),
      [
        "id: handmade",
        "name: Handmade",
        "week_start: 2026-06-08",
        "week_end: 2026-06-14",
        "items:",
        "  - ingredient_name: Apples",
        "    total_quantity: 6",
        "    checked: true",
        "  - unit: g", // no ingredient_name → skipped
      ].join("\n"),
    );

    const loaded = await repo.getById("handmade");
    expect(loaded!.name).toBe("Handmade");
    expect(loaded!.items).toHaveLength(1);
    expect(loaded!.items![0].ingredientName).toBe("Apples");
    expect(loaded!.items![0].totalQuantity?.toString()).toBe("6");
    expect(loaded!.items![0].checked).toBe(true);
  });
});
