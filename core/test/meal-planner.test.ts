/** Port of backend/tests/unit/test_meal_planner.py. */
import { describe, it, expect } from "vitest";
import { Decimal } from "decimal.js";

import {
  MealPlanAggregator,
  MealType,
  MacroProfile,
  type PlannedMeal,
} from "../src/index";

function meal(
  date: string,
  opts: { servings: number | string; cals: number; protein?: number; mealType?: MealType },
): PlannedMeal {
  const { servings, cals, protein = 0, mealType = MealType.DINNER } = opts;
  return {
    date,
    mealType,
    servingsPlanned: new Decimal(servings),
    perServing: new MacroProfile({
      calories: new Decimal(cals),
      protein: new Decimal(protein),
    }),
  };
}

describe("MealPlanAggregator", () => {
  it("scales per-serving by planned servings", () => {
    const summary = new MealPlanAggregator().aggregate([
      meal("2026-06-01", { servings: 2, cals: 100, protein: 5 }),
    ]);
    expect(summary.totals.amounts.calories.toString()).toBe("200");
    expect(summary.totals.amounts.protein.toString()).toBe("10");
    expect(summary.days.length).toBe(1);
    expect(summary.days[0].date).toBe("2026-06-01");
  });

  it("groups by day and sums the week total", () => {
    const mon = "2026-06-01";
    const tue = "2026-06-02";
    const summary = new MealPlanAggregator().aggregate([
      meal(mon, { servings: 1, cals: 300 }),
      meal(mon, { servings: 1, cals: 200, mealType: MealType.LUNCH }),
      meal(tue, { servings: 2, cals: 250 }),
    ]);

    expect(summary.days.map((day) => day.date)).toEqual([mon, tue]);
    expect(summary.days[0].totals.amounts.calories.toString()).toBe("500"); // 300 + 200
    expect(summary.days[1].totals.amounts.calories.toString()).toBe("500"); // 250 * 2
    expect(summary.totals.amounts.calories.toString()).toBe("1000");
  });

  it("handles fractional servings", () => {
    const summary = new MealPlanAggregator().aggregate([
      meal("2026-06-01", { servings: "0.5", cals: 400 }),
    ]);
    expect(summary.days[0].totals.amounts.calories.toString()).toBe("200");
  });

  it("zeroes an empty plan", () => {
    const summary = new MealPlanAggregator().aggregate([]);
    expect(summary.days).toEqual([]);
    expect(summary.totals.amounts).toEqual({});
  });
});
