/**
 * MacroCalculator — ingredient-level macro math. Port of
 * `domain/services/macro_calculator.py`.
 *
 * Pure domain service: no DB, no network. Fed a per-100g nutrient index (keyed
 * by FDC id) and returns *both* the per-line breakdown and the recipe totals.
 * The per-line breakdown is the point — it lets the UI answer "which ingredient
 * is driving the fat / sodium?".
 *
 *     contribution(nutrient) = (gramWeight / 100) * amountPer100g
 */
import { Decimal } from "decimal.js";

import type { Recipe, RecipeIngredient } from "../entities/recipe";
import type { Id } from "../identity";
import { MacroProfile, type NutrientAmount } from "../value-objects/macro";

const HUNDRED = new Decimal(100);

/**
 * Maps the recipe's hand-entered per-serving fields to the canonical macro keys
 * the rest of the app uses (matches the frontend's MACRO_ORDER / FDC nutrient
 * names). Carbs/fiber/sodium use the long canonical key.
 */
const MANUAL_FIELD_TO_KEY = {
  caloriesPerServing: "calories",
  proteinPerServing: "protein",
  fatPerServing: "fat",
  carbsPerServing: "carbohydrate",
  fiberPerServing: "fiber",
  sodiumPerServing: "sodium",
} as const;

type ManualField = keyof typeof MANUAL_FIELD_TO_KEY;

/** A nutrient index keyed by FDC id, each value a list of per-100g amounts. */
export type NutrientIndex = ReadonlyMap<number, readonly NutrientAmount[]>;

/**
 * The recipe's hand-entered per-serving macros, or null if none are set. Only
 * includes fields the user actually filled in, so an empty form leaves the
 * ingredient-level path (USDA links) untouched.
 */
export function manualPerServing(recipe: Recipe): MacroProfile | null {
  const amounts: Record<string, Decimal> = {};
  let any = false;
  for (const field of Object.keys(MANUAL_FIELD_TO_KEY) as ManualField[]) {
    const value = recipe[field];
    if (value !== null && value !== undefined) {
      amounts[MANUAL_FIELD_TO_KEY[field]] = value;
      any = true;
    }
  }
  return any ? new MacroProfile(amounts) : null;
}

/** One recipe ingredient's macro contribution. */
export interface LineMacro {
  ingredientName: string;
  profile: MacroProfile;
  resolved: boolean;
  recipeIngredientId: Id | null;
  // External USDA FoodData Central id (an integer owned by USDA), not our identity.
  fdcId: number | null;
  gramWeight: Decimal | null;
}

export interface RecipeMacroBreakdown {
  lines: LineMacro[];
  totals: MacroProfile;
  perServing: MacroProfile | null;
  unresolvedCount: number;
}

export class MacroCalculator {
  lineProfile(line: RecipeIngredient, nutrientIndex: NutrientIndex): LineMacro {
    const fdcId = line.usdaFdcId ?? line.ingredient.usdaFdcId ?? null;
    const amounts = fdcId !== null ? nutrientIndex.get(fdcId) : undefined;
    const gramWeight = line.gramWeight ?? null;

    if (fdcId === null || gramWeight === null || !amounts || amounts.length === 0) {
      return {
        ingredientName: line.ingredient.name,
        profile: new MacroProfile({}),
        resolved: false,
        recipeIngredientId: line.id ?? null,
        fdcId,
        gramWeight,
      };
    }

    const factor = gramWeight.div(HUNDRED);
    const profileAmounts: Record<string, Decimal> = {};
    for (const na of amounts) {
      profileAmounts[na.nutrient] = factor.times(na.amount);
    }
    return {
      ingredientName: line.ingredient.name,
      profile: new MacroProfile(profileAmounts),
      resolved: true,
      recipeIngredientId: line.id ?? null,
      fdcId,
      gramWeight,
    };
  }

  calculate(recipe: Recipe, nutrientIndex: NutrientIndex): RecipeMacroBreakdown {
    // Hand-entered per-serving macros win when present: the primary workflow.
    // Totals scale up by the yield; no per-ingredient lines.
    const manual = manualPerServing(recipe);
    if (manual !== null) {
      const servings = recipe.servings && recipe.servings > 0 ? recipe.servings : 1;
      const totals = manual.scale(new Decimal(servings));
      return { lines: [], totals, perServing: manual, unresolvedCount: 0 };
    }

    const lines = (recipe.ingredients ?? []).map((line) =>
      this.lineProfile(line, nutrientIndex),
    );

    let totals = new MacroProfile({});
    for (const line of lines) {
      totals = totals.add(line.profile);
    }

    let perServing: MacroProfile | null = null;
    if (recipe.servings && recipe.servings > 0) {
      const divisor = new Decimal(recipe.servings);
      const per: Record<string, Decimal> = {};
      for (const [nutrient, amount] of Object.entries(totals.amounts)) {
        per[nutrient] = amount.div(divisor);
      }
      perServing = new MacroProfile(per);
    }

    const unresolvedCount = lines.filter((l) => !l.resolved).length;
    return { lines, totals, perServing, unresolvedCount };
  }
}
