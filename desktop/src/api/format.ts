/**
 * Presentation helpers for macro nutrients.
 *
 * The macro breakdown serializes amounts as strings (Decimal on the wire) and
 * drops units, so we keep a canonical label/unit/order table here. These names
 * mirror the backend's TRACKED_NUTRIENTS canonical keys.
 */

export const MACRO_ORDER = [
  "calories",
  "protein",
  "fat",
  "saturated_fat",
  "carbohydrate",
  "fiber",
  "sugar",
  "sodium",
] as const;

const MACRO_LABEL: Record<string, string> = {
  calories: "Calories",
  protein: "Protein",
  fat: "Fat",
  saturated_fat: "Sat. fat",
  carbohydrate: "Carbs",
  fiber: "Fiber",
  sugar: "Sugar",
  sodium: "Sodium",
};

const MACRO_UNIT: Record<string, string> = {
  calories: "kcal",
  protein: "g",
  fat: "g",
  saturated_fat: "g",
  carbohydrate: "g",
  fiber: "g",
  sugar: "g",
  sodium: "mg",
};

export function macroLabel(key: string): string {
  return MACRO_LABEL[key] ?? key;
}

export function macroUnit(key: string): string {
  return MACRO_UNIT[key] ?? "";
}

/** Order a set of macro keys by the canonical order, unknowns last. */
export function orderedMacroKeys(keys: Iterable<string>): string[] {
  const present = new Set(keys);
  const known = MACRO_ORDER.filter((k) => present.has(k));
  const extra = [...present].filter((k) => !MACRO_ORDER.includes(k as never)).sort();
  return [...known, ...extra];
}

/** Trim trailing zeros from a decimal string for compact display. */
export function formatAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  // Keep up to 1 decimal place; integers render clean.
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
