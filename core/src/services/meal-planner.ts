/**
 * MealPlanAggregator — per-day and whole-range macro totals for a meal plan.
 * Port of `domain/services/meal_planner.py`.
 *
 * Fed each planned meal's *per-serving* macro profile (computed upstream by
 * MacroCalculator) plus how many servings are planned, and it scales + groups
 * them by date. Powers the calendar's "calories this day / this week" rollups,
 * reusing the same macro math as the recipe view.
 */
import type { Decimal } from "decimal.js";

import type { MealType } from "../entities/meal";
import { MacroProfile } from "../value-objects/macro";

/**
 * A meal event reduced to what the aggregator needs: when, how much, and the
 * recipe's per-serving macro profile. `date` is an ISO `YYYY-MM-DD` string.
 */
export interface PlannedMeal {
  date: string;
  mealType: MealType;
  servingsPlanned: Decimal;
  perServing: MacroProfile;
}

export interface DayMacros {
  date: string;
  totals: MacroProfile;
}

export interface WeekMacroSummary {
  days: DayMacros[];
  totals: MacroProfile;
}

export class MealPlanAggregator {
  aggregate(meals: readonly PlannedMeal[]): WeekMacroSummary {
    const byDay = new Map<string, MacroProfile>();
    for (const meal of meals) {
      const scaled = meal.perServing.scale(meal.servingsPlanned);
      byDay.set(meal.date, (byDay.get(meal.date) ?? new MacroProfile({})).add(scaled));
    }

    // ISO date strings sort chronologically.
    const days: DayMacros[] = [...byDay.keys()]
      .sort()
      .map((date) => ({ date, totals: byDay.get(date)! }));

    let grand = new MacroProfile({});
    for (const day of days) {
      grand = grand.add(day.totals);
    }

    return { days, totals: grand };
  }
}
