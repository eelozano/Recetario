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

export interface ShoppingDemand {
  ingredientName: string;
  normalizedName: string;
  quantity: Decimal | null;
  unit: string | null;
  ingredientId?: number | null;
  sourceEventId?: number | null;
}

export interface AggregatedItem {
  ingredientName: string;
  unit: string | null;
  totalQuantity: Decimal | null;
  ingredientId: number | null;
  sourceEventIds: number[];
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

      const sourceEventIds: number[] = [];
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
