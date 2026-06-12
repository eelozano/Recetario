/**
 * Cross-entity read/compute orchestration over the core repositories
 * (Architecture v2, step 3). The repositories themselves are single-entity CRUD;
 * the week macro rollup and shopping-list generation need to join recipes with
 * meal events, so that glue lives here — a faithful TS port of the Python
 * `CalculateWeekMacros` and `GenerateWeeklyShoppingList` use cases.
 *
 * In the file world there is no USDA nutrient cache, so macros come solely from
 * each recipe's hand-entered per-serving fields (the app's primary workflow since
 * the USDA-linking UI was removed). The MacroCalculator is fed an empty index.
 */
import { Decimal } from "decimal.js";
import {
  MacroCalculator,
  MacroProfile,
  MealPlanAggregator,
  ShoppingAggregator,
  asShoppingCategory,
  categorizeIngredient,
  manualPerServing,
  type MealEvent,
  type NutrientIndex,
  type PlannedMeal,
  type Recipe,
  type ShoppingDemand,
  type ShoppingList,
  type WeekMacroSummary,
} from "@recetario/core";

import { getRepos } from "./repos";

const ONE = new Decimal(1);
/** No USDA cache in the file world — macros come from manual per-serving fields. */
const EMPTY_INDEX: NutrientIndex = new Map();

const macroCalculator = new MacroCalculator();
const mealAggregator = new MealPlanAggregator();
const shoppingAggregator = new ShoppingAggregator();

/** A recipe's per-serving macro profile (manual macros win; else empty). */
export function recipePerServing(recipe: Recipe): MacroProfile {
  const manual = manualPerServing(recipe);
  if (manual !== null) return manual;
  const breakdown = macroCalculator.calculate(recipe, EMPTY_INDEX);
  return breakdown.perServing ?? breakdown.totals;
}

/** The per-line + total macro breakdown for one recipe (per-serving cards). */
export function recipeMacros(recipe: Recipe) {
  return macroCalculator.calculate(recipe, EMPTY_INDEX);
}

export interface WeekPlan {
  /** Events in range, each with `recipeTitle` joined in for the calendar chips. */
  events: MealEvent[];
  macros: WeekMacroSummary;
}

/**
 * Load a week's meal events plus per-day / whole-week macro rollups, resolving
 * each event's recipe once (cached) for both the chip title and its macros.
 */
export async function loadWeekPlan(start: string, end: string): Promise<WeekPlan> {
  const { meals, recipes } = await getRepos();
  const events = await meals.listRange(start, end);

  const cache = new Map<string, Recipe | null>();
  const recipeFor = async (id: string): Promise<Recipe | null> => {
    if (!cache.has(id)) cache.set(id, await recipes.getById(id));
    return cache.get(id) ?? null;
  };

  const joined: MealEvent[] = [];
  const planned: PlannedMeal[] = [];
  for (const event of events) {
    const recipe = await recipeFor(event.recipeId);
    joined.push({ ...event, recipeTitle: recipe?.title ?? null });
    planned.push({
      date: event.date,
      mealType: event.mealType,
      servingsPlanned: event.servingsPlanned ?? ONE,
      perServing: recipe ? recipePerServing(recipe) : new MacroProfile({}),
    });
  }

  return { events: joined, macros: mealAggregator.aggregate(planned) };
}

/**
 * Aggregate a week's scheduled meals into a grocery list and persist it. Scales
 * each recipe's ingredient quantities by planned servings ÷ recipe yield, then
 * dedupes + sums by (ingredient, unit) — matching the Python use case.
 */
export async function generateShoppingList(
  weekStart: string,
  weekEnd: string,
): Promise<ShoppingList> {
  const { meals, recipes, shopping, categoryOverrides } = await getRepos();
  const events = await meals.listRange(weekStart, weekEnd);
  const overrides = await categoryOverrides.load();

  const cache = new Map<string, Recipe | null>();
  const demands: ShoppingDemand[] = [];
  for (const event of events) {
    if (!cache.has(event.recipeId)) {
      cache.set(event.recipeId, await recipes.getById(event.recipeId));
    }
    const recipe = cache.get(event.recipeId);
    if (!recipe) continue;

    const servings = recipe.servings && recipe.servings > 0 ? recipe.servings : 1;
    const factor = (event.servingsPlanned ?? ONE).div(servings);
    for (const line of recipe.ingredients ?? []) {
      const normalizedName = line.ingredient.normalizedName;
      demands.push({
        ingredientName: line.ingredient.name,
        normalizedName,
        quantity: line.quantity != null ? line.quantity.times(factor) : null,
        unit: line.unit ?? null,
        // The user's saved preference outranks the import-time (LLM) category,
        // which outranks the static map.
        category:
          overrides.get(normalizedName) ??
          asShoppingCategory(line.category) ??
          categorizeIngredient(normalizedName),
        ingredientId: line.ingredient.id ?? null,
        sourceEventId: event.id ?? null,
      });
    }
  }

  const items = shoppingAggregator.aggregate(demands);
  return shopping.create({
    name: `Groceries — week of ${weekStart}`,
    weekStart,
    weekEnd,
    items: items.map((it) => ({
      ingredientName: it.ingredientName,
      unit: it.unit,
      totalQuantity: it.totalQuantity,
      category: it.category,
      ingredientId: it.ingredientId,
      sourceEventIds: it.sourceEventIds,
    })),
  });
}

/** Flatten a MacroProfile's Decimal amounts to display strings for the cards. */
export function profileToStrings(profile: MacroProfile): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(profile.amounts)) {
    out[key] = value.toString();
  }
  return out;
}
