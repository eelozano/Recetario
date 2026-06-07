/**
 * Nutrition value objects. Port of `domain/value_objects/macro.py`.
 *
 * `MacroProfile` is an immutable, additive bundle of nutrient amounts (per
 * recipe, line, or meal). All arithmetic uses decimal.js so totals match the
 * Python `decimal.Decimal` results exactly.
 */
import { Decimal } from "decimal.js";

export interface NutrientAmount {
  nutrient: string;
  amount: Decimal;
  unit: string;
}

export class MacroProfile {
  /** Nutrient key → amount. Insertion order is preserved (mirrors the Python dict). */
  readonly amounts: Record<string, Decimal>;

  constructor(amounts: Record<string, Decimal> = {}) {
    this.amounts = amounts;
  }

  /** Sum two profiles; shared keys add, new keys append (Python `__add__`). */
  add(other: MacroProfile): MacroProfile {
    const merged: Record<string, Decimal> = { ...this.amounts };
    for (const [nutrient, amount] of Object.entries(other.amounts)) {
      merged[nutrient] = (merged[nutrient] ?? new Decimal(0)).plus(amount);
    }
    return new MacroProfile(merged);
  }

  /** Multiply every nutrient amount by `factor` (e.g. servings planned). */
  scale(factor: Decimal): MacroProfile {
    const scaled: Record<string, Decimal> = {};
    for (const [nutrient, amount] of Object.entries(this.amounts)) {
      scaled[nutrient] = amount.times(factor);
    }
    return new MacroProfile(scaled);
  }
}
