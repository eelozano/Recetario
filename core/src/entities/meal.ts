/**
 * Meal-calendar entities. Port of `domain/entities/meal.py`.
 *
 * A `MealEvent` schedules one recipe into a meal slot on a given date. A "week"
 * is simply the events whose date falls in a range — no separate week entity.
 * Dates are ISO `YYYY-MM-DD` strings (sortable, JSON-friendly, valid Map keys).
 */
import type { Decimal } from "decimal.js";

export enum MealType {
  BREAKFAST = "breakfast",
  LUNCH = "lunch",
  DINNER = "dinner",
  SNACK = "snack",
}

export interface MealEvent {
  date: string;
  mealType: MealType;
  recipeId: number;
  servingsPlanned?: Decimal;
  notes?: string | null;
  id?: number | null;
  /** Read-time convenience populated by the repository for the calendar view. */
  recipeTitle?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
