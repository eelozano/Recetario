/**
 * ShoppingAggregator — collapse a week's recipe ingredients into a grocery list.
 * Port of `domain/services/shopping_aggregator.py`.
 *
 * Fed `ShoppingDemand`s (one per recipe ingredient line, already scaled for the
 * planned servings by the caller) and groups them by canonical ingredient *and
 * unit*, summing quantities.
 *
 * Why group by unit too: with no density data we cannot honestly convert
 * "2 cups" + "100 g" of the same ingredient into one number. Lines that share a
 * unit are summed; different units stay separate, clearly-labelled items.
 * Quantity-less lines ("salt to taste") are preserved as un-summed items.
 */
import { Decimal } from "decimal.js";

import type { Id } from "../identity";

export interface ShoppingDemand {
  ingredientName: string;
  normalizedName: string;
  quantity: Decimal | null;
  unit: string | null;
  /**
   * Grocery-aisle category id (preset or user-defined custom); resolved per
   * normalizedName across all demands.
   */
  category?: string | null;
  ingredientId?: Id | null;
  sourceEventId?: Id | null;
}

export interface AggregatedItem {
  ingredientName: string;
  unit: string | null;
  totalQuantity: Decimal | null;
  category: string | null;
  ingredientId: Id | null;
  sourceEventIds: Id[];
}

function unitKey(unit: string | null): string | null {
  if (unit === null || unit === undefined) {
    return null;
  }
  const cleaned = unit.trim().toLowerCase();
  return cleaned || null;
}

export class ShoppingAggregator {
  aggregate(demands: readonly ShoppingDemand[]): AggregatedItem[] {
    const groups = new Map<string, ShoppingDemand[]>();
    const order: string[] = [];
    // Category is resolved per normalizedName — not per (name, unit) group — so
    // the same ingredient can never land under two headers when sources disagree.
    const categoryByName = new Map<string, string>();

    for (const demand of demands) {
      // Composite (normalizedName, unitKey) key; JSON keeps null distinct from "null".
      const key = JSON.stringify([demand.normalizedName, unitKey(demand.unit)]);
      let bucket = groups.get(key);
      if (bucket === undefined) {
        bucket = [];
        groups.set(key, bucket);
        order.push(key);
      }
      bucket.push(demand);
      if (demand.category != null && !categoryByName.has(demand.normalizedName)) {
        categoryByName.set(demand.normalizedName, demand.category);
      }
    }

    const items: AggregatedItem[] = [];
    for (const key of order) {
      const members = groups.get(key)!;
      const quantities = members
        .map((m) => m.quantity)
        .filter((q): q is Decimal => q !== null && q !== undefined);
      const total = quantities.length
        ? quantities.reduce((sum, q) => sum.plus(q), new Decimal(0))
        : null;

      const ingredientId =
        members.find((m) => m.ingredientId !== null && m.ingredientId !== undefined)
          ?.ingredientId ?? null;

      const sourceEventIds: Id[] = [];
      for (const m of members) {
        if (
          m.sourceEventId !== null &&
          m.sourceEventId !== undefined &&
          !sourceEventIds.includes(m.sourceEventId)
        ) {
          sourceEventIds.push(m.sourceEventId);
        }
      }

      items.push({
        ingredientName: members[0].ingredientName,
        unit: members[0].unit,
        totalQuantity: total,
        category: categoryByName.get(members[0].normalizedName) ?? null,
        ingredientId,
        sourceEventIds,
      });
    }

    // Alphabetical for a shopper-friendly list.
    items.sort((a, b) =>
      a.ingredientName.toLowerCase().localeCompare(b.ingredientName.toLowerCase()),
    );
    return items;
  }
}
