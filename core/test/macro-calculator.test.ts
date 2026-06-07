/** Port of backend/tests/unit/test_macro_calculator.py. */
import { describe, it, expect } from "vitest";
import { Decimal } from "decimal.js";

import {
  MacroCalculator,
  type NutrientAmount,
  type NutrientIndex,
  type Recipe,
} from "../src/index";
import { plain } from "./helpers";

function makeRecipe(): Recipe {
  return {
    title: "Onion soup",
    servings: 2,
    ingredients: [
      {
        id: 1,
        position: 0,
        ingredient: { name: "Onion", normalizedName: "onion" },
        usdaFdcId: 170000,
        gramWeight: new Decimal("200"),
      },
      {
        id: 2,
        position: 1,
        ingredient: { name: "Salt", normalizedName: "salt" },
      },
    ],
  };
}

const INDEX: NutrientIndex = new Map<number, NutrientAmount[]>([
  [
    170000,
    [
      { nutrient: "calories", amount: new Decimal("40"), unit: "kcal" },
      { nutrient: "protein", amount: new Decimal("1.1"), unit: "g" },
    ],
  ],
]);

describe("MacroCalculator", () => {
  it("scales per-line contribution by gram weight", () => {
    const breakdown = new MacroCalculator().calculate(makeRecipe(), INDEX);

    const onion = breakdown.lines[0];
    expect(onion.resolved).toBe(true);
    // 200 g => factor 2 over the per-100g basis.
    expect(onion.profile.amounts.calories.toString()).toBe("80");
    expect(onion.profile.amounts.protein.toString()).toBe("2.2");
  });

  it("an unresolved line contributes nothing", () => {
    const breakdown = new MacroCalculator().calculate(makeRecipe(), INDEX);
    const salt = breakdown.lines[1];
    expect(salt.resolved).toBe(false);
    expect(plain(salt.profile)).toEqual({});
    expect(breakdown.unresolvedCount).toBe(1);
  });

  it("computes totals and per-serving", () => {
    const breakdown = new MacroCalculator().calculate(makeRecipe(), INDEX);
    expect(breakdown.totals.amounts.calories.toString()).toBe("80");
    expect(breakdown.perServing).not.toBeNull();
    expect(breakdown.perServing!.amounts.calories.toString()).toBe("40");
    expect(breakdown.perServing!.amounts.protein.toString()).toBe("1.1");
  });

  it("no servings means no per-serving", () => {
    const recipe = makeRecipe();
    recipe.servings = null;
    const breakdown = new MacroCalculator().calculate(recipe, INDEX);
    expect(breakdown.perServing).toBeNull();
  });

  // --- Manual per-serving macros (#18): the primary macro workflow ---

  it("manual macros take precedence over ingredient links", () => {
    const recipe = makeRecipe(); // has a USDA-linked onion in INDEX
    recipe.caloriesPerServing = new Decimal("250");
    recipe.proteinPerServing = new Decimal("12");

    const breakdown = new MacroCalculator().calculate(recipe, INDEX);

    expect(breakdown.perServing).not.toBeNull();
    expect(plain(breakdown.perServing!)).toEqual({ calories: "250", protein: "12" });
    // Totals scale by the 2-serving yield; ingredient breakdown is bypassed.
    expect(plain(breakdown.totals)).toEqual({ calories: "500", protein: "24" });
    expect(breakdown.lines).toEqual([]);
    expect(breakdown.unresolvedCount).toBe(0);
  });

  it("manual macros map carbs/fiber/sodium to canonical keys", () => {
    const recipe = makeRecipe();
    recipe.servings = 1;
    recipe.carbsPerServing = new Decimal("30");
    recipe.fiberPerServing = new Decimal("5");
    recipe.sodiumPerServing = new Decimal("400");

    const breakdown = new MacroCalculator().calculate(recipe, INDEX);

    expect(breakdown.perServing).not.toBeNull();
    expect(plain(breakdown.perServing!)).toEqual({
      carbohydrate: "30",
      fiber: "5",
      sodium: "400",
    });
    // One serving: totals equal per-serving.
    expect(plain(breakdown.totals)).toEqual(plain(breakdown.perServing!));
  });

  it("manual macros without servings assume one serving", () => {
    const recipe = makeRecipe();
    recipe.servings = null;
    recipe.caloriesPerServing = new Decimal("180");

    const breakdown = new MacroCalculator().calculate(recipe, INDEX);

    expect(plain(breakdown.perServing!)).toEqual({ calories: "180" });
    expect(plain(breakdown.totals)).toEqual({ calories: "180" });
  });

  it("empty manual macros fall back to the ingredient path", () => {
    const breakdown = new MacroCalculator().calculate(makeRecipe(), INDEX);
    expect(breakdown.totals.amounts.calories.toString()).toBe("80");
    expect(breakdown.lines.length).toBe(2);
  });
});
