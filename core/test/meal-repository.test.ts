/** MealEventRepository against the real Node filesystem in a temp dir. */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { mkdtemp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Decimal } from "decimal.js";

import { MealEventRepository, MealType, type MealEvent } from "../src/index";
import { NodeFileSystem } from "../src/storage/adapters/node-fs";

const fs = new NodeFileSystem();
let base: string;
let repo: MealEventRepository;

beforeEach(async () => {
  base = await mkdtemp(join(tmpdir(), "recetario-meals-"));
  repo = new MealEventRepository(fs, base);
});

afterEach(async () => {
  await rm(base, { recursive: true, force: true });
});

function event(date: string, extra: Partial<MealEvent> = {}): MealEvent {
  return { date, mealType: MealType.DINNER, recipeId: "recipe-1", ...extra };
}

describe("MealEventRepository", () => {
  it("creates an event into its month file and round-trips via getById", async () => {
    const saved = await repo.create(
      event("2026-06-01", { servingsPlanned: new Decimal("2") }),
    );

    expect(saved.id).toMatch(/[0-9a-f-]{36}/);
    expect(saved.createdAt).toBeTruthy();

    const files = await readdir(join(base, "meal-calendar"));
    expect(files).toEqual(["meal-calendar-2026-06.yaml"]);

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.date).toBe("2026-06-01");
    expect(loaded!.recipeId).toBe("recipe-1");
    expect(loaded!.servingsPlanned?.toString()).toBe("2");
  });

  it("lists events within an inclusive date range, spanning months", async () => {
    await repo.create(event("2026-05-31"));
    await repo.create(event("2026-06-15"));
    await repo.create(event("2026-07-02"));

    const inJune = await repo.listRange("2026-06-01", "2026-06-30");
    expect(inJune.map((e) => e.date)).toEqual(["2026-06-15"]);

    const spanning = await repo.listRange("2026-05-15", "2026-07-01");
    expect(spanning.map((e) => e.date).sort()).toEqual(["2026-05-31", "2026-06-15"]);
  });

  it("moves an event between month files when its date changes, no duplicate", async () => {
    const saved = await repo.create(event("2026-06-10"));
    await repo.update({ ...saved, date: "2026-07-10" });

    const files = (await readdir(join(base, "meal-calendar"))).sort();
    expect(files).toEqual(["meal-calendar-2026-07.yaml"]); // June file removed (now empty)

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.date).toBe("2026-07-10");
    expect(await repo.listRange("2026-06-01", "2026-06-30")).toEqual([]);
  });

  it("updates an event in place within the same month", async () => {
    const saved = await repo.create(event("2026-06-10", { servingsPlanned: new Decimal("1") }));
    await repo.update({ ...saved, servingsPlanned: new Decimal("4"), mealType: MealType.LUNCH });

    const loaded = await repo.getById(saved.id!);
    expect(loaded!.servingsPlanned?.toString()).toBe("4");
    expect(loaded!.mealType).toBe(MealType.LUNCH);
    const events = await repo.listRange("2026-06-01", "2026-06-30");
    expect(events).toHaveLength(1); // not duplicated
  });

  it("deletes an event and removes the now-empty month file", async () => {
    const saved = await repo.create(event("2026-06-10"));
    await repo.delete(saved.id!);

    expect(await repo.getById(saved.id!)).toBeNull();
    const dir = join(base, "meal-calendar");
    expect(await readdir(dir)).toEqual([]); // empty month file gone
  });

  it("best-effort reads a hand-written month file, skipping placeless events", async () => {
    const dir = join(base, "meal-calendar");
    await mkdir(dir, { recursive: true });
    await writeFile(
      join(dir, "meal-calendar-2026-06.yaml"),
      [
        "month: 2026-06",
        "events:",
        "  - date: 2026-06-03",
        "    meal_type: breakfast",
        "    recipe_id: r-99",
        "  - meal_type: dinner", // no date/recipe_id → skipped
        "    notes: orphan",
      ].join("\n"),
    );

    const events = await repo.listRange("2026-06-01", "2026-06-30");
    expect(events).toHaveLength(1);
    expect(events[0].recipeId).toBe("r-99");
    expect(events[0].mealType).toBe(MealType.BREAKFAST);
  });
});
