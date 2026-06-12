/** Port of backend/tests/unit/test_shopping_aggregator.py. */
import { describe, it, expect } from "vitest";
import { Decimal } from "decimal.js";

import {
  ShoppingAggregator,
  type ShoppingCategory,
  type ShoppingDemand,
} from "../src/index";

function d(
  name: string,
  qty: number | null,
  unit: string | null,
  opts: {
    event?: string;
    ingredientId?: string | null;
    category?: ShoppingCategory | null;
  } = {},
): ShoppingDemand {
  const { event = "e1", ingredientId = null, category = null } = opts;
  return {
    ingredientName: name,
    normalizedName: name.trim().toLowerCase(),
    quantity: qty !== null ? new Decimal(qty) : null,
    unit,
    category,
    ingredientId,
    sourceEventId: event,
  };
}

describe("ShoppingAggregator", () => {
  it("sums the same ingredient and unit", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 2, "pc", { event: "e1" }),
      d("Onion", 3, "pc", { event: "e2" }),
    ]);
    expect(items.length).toBe(1);
    expect(items[0].ingredientName).toBe("Onion");
    expect(items[0].totalQuantity!.toString()).toBe("5");
    expect(items[0].sourceEventIds).toEqual(["e1", "e2"]);
  });

  it("keeps the same ingredient in different units separate", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 2, "pc"),
      d("Onion", 100, "g"),
    ]);
    expect(items.length).toBe(2);
    expect(new Set(items.map((i) => i.unit))).toEqual(new Set(["pc", "g"]));
  });

  it("groups units case-insensitively", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Flour", 1, "Cup"),
      d("Flour", 2, "cup"),
    ]);
    expect(items.length).toBe(1);
    expect(items[0].totalQuantity!.toString()).toBe("3");
  });

  it("preserves quantity-less items", () => {
    const items = new ShoppingAggregator().aggregate([d("Salt", null, null)]);
    expect(items.length).toBe(1);
    expect(items[0].totalQuantity).toBeNull();
  });

  it("orders alphabetically", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Zucchini", 1, "pc"),
      d("Apple", 1, "pc"),
      d("Mango", 1, "pc"),
    ]);
    expect(items.map((i) => i.ingredientName)).toEqual(["Apple", "Mango", "Zucchini"]);
  });

  it("carries the first non-null ingredient id", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 1, "pc", { ingredientId: null }),
      d("Onion", 1, "pc", { ingredientId: "i7" }),
    ]);
    expect(items[0].ingredientId).toBe("i7");
  });

  it("dedupes source event ids", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 1, "pc", { event: "e5" }),
      d("Onion", 1, "pc", { event: "e5" }),
    ]);
    expect(items[0].sourceEventIds).toEqual(["e5"]);
  });

  it("carries the demand category onto the item", () => {
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 1, "pc", { category: "produce" }),
    ]);
    expect(items[0].category).toBe("produce");
  });

  it("resolves category per normalizedName so duplicates cannot disagree", () => {
    // Same ingredient in two units (two output items), categorized by only one
    // recipe — both items, including the uncategorized line, get the category.
    const items = new ShoppingAggregator().aggregate([
      d("Onion", 2, "pc", { category: "produce" }),
      d("Onion", 100, "g", { category: null }),
    ]);
    expect(items.length).toBe(2);
    expect(items.every((i) => i.category === "produce")).toBe(true);
  });

  it("defaults category to null when no demand has one", () => {
    const items = new ShoppingAggregator().aggregate([d("Mystery", 1, "pc")]);
    expect(items[0].category).toBeNull();
  });
});
