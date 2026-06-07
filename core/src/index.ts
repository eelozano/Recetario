/** Public surface of the portable domain core. */

export type { Id } from "./identity";

export { MacroProfile } from "./value-objects/macro";
export type { NutrientAmount } from "./value-objects/macro";

export * from "./entities";

export { MacroCalculator, manualPerServing } from "./services/macro-calculator";
export type {
  LineMacro,
  RecipeMacroBreakdown,
  NutrientIndex,
} from "./services/macro-calculator";

export { ShoppingAggregator } from "./services/shopping-aggregator";
export type {
  ShoppingDemand,
  AggregatedItem,
} from "./services/shopping-aggregator";

export { MealPlanAggregator } from "./services/meal-planner";
export type {
  PlannedMeal,
  DayMacros,
  WeekMacroSummary,
} from "./services/meal-planner";

export * from "./storage";
