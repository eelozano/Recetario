/**
 * Ingredient-name normalization.
 *
 * `normalizedName` is what the shopping aggregator groups by, but it's redundant
 * with `name`, so we don't persist it — it's recomputed on read. Rule: trim +
 * lowercase (matches the original Python `normalized_name` usage and the
 * aggregator tests).
 */
export function normalizeIngredientName(name: string): string {
  return name.trim().toLowerCase();
}
