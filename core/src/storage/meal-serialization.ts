/**
 * Meal-calendar serialization. Events are stored one file per month:
 * `meal-calendar/meal-calendar-YYYY-MM.yaml` with `{ month, events: [...] }`.
 *
 * `recipe_title` is a read-time convenience the repository fills for the calendar
 * view, so it is NOT persisted. Reading is best-effort: an event missing a date
 * or recipe_id can't be placed and is skipped; other fields default.
 */
import { Decimal } from "decimal.js";

import { type MealEvent, MealType } from "../entities/meal";
import { asDecimal, asRecord, asString, decimalToNumber } from "./coerce";
import { newId } from "./id";
import { dumpYaml, loadYaml } from "./yaml";

const ONE = new Decimal(1);

const MEAL_ORDER: Record<MealType, number> = {
  [MealType.BREAKFAST]: 0,
  [MealType.LUNCH]: 1,
  [MealType.DINNER]: 2,
  [MealType.SNACK]: 3,
};

function mealTypeOf(value: unknown): MealType {
  const s = asString(value);
  return s !== undefined && (Object.values(MealType) as string[]).includes(s)
    ? (s as MealType)
    : MealType.DINNER;
}

function eventToData(event: MealEvent): Record<string, unknown> {
  const out: Record<string, unknown> = {
    id: event.id,
    date: event.date,
    meal_type: event.mealType,
    recipe_id: event.recipeId,
    servings_planned: decimalToNumber(event.servingsPlanned ?? ONE),
  };
  if (event.notes) out.notes = event.notes;
  if (event.createdAt) out.created_at = event.createdAt;
  if (event.updatedAt) out.updated_at = event.updatedAt;
  return out;
}

function eventFromData(value: unknown): MealEvent | null {
  const row = asRecord(value);
  const date = asString(row.date);
  const recipeId = asString(row.recipe_id);
  if (date === undefined || recipeId === undefined) return null;

  const event: MealEvent = {
    id: asString(row.id) ?? newId(),
    date,
    mealType: mealTypeOf(row.meal_type),
    recipeId,
    servingsPlanned: asDecimal(row.servings_planned) ?? ONE,
  };
  const notes = asString(row.notes);
  if (notes !== undefined) event.notes = notes;
  const createdAt = asString(row.created_at);
  if (createdAt !== undefined) event.createdAt = createdAt;
  const updatedAt = asString(row.updated_at);
  if (updatedAt !== undefined) event.updatedAt = updatedAt;
  return event;
}

/** Sort events for a stable on-disk order: by date, then meal slot. */
function sortEvents(events: MealEvent[]): MealEvent[] {
  return [...events].sort(
    (a, b) =>
      a.date.localeCompare(b.date) || MEAL_ORDER[a.mealType] - MEAL_ORDER[b.mealType],
  );
}

export function monthFileToString(month: string, events: MealEvent[]): string {
  const data = { month, events: sortEvents(events).map(eventToData) };
  return dumpYaml(data);
}

export function eventsFromMonthFile(content: string): MealEvent[] {
  let data: Record<string, unknown> = {};
  try {
    data = asRecord(loadYaml(content));
  } catch {
    return [];
  }
  if (!Array.isArray(data.events)) return [];
  const events: MealEvent[] = [];
  for (const row of data.events) {
    const event = eventFromData(row);
    if (event) events.push(event);
  }
  return events;
}
