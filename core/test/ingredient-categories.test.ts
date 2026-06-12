import { describe, it, expect } from "vitest";

import {
  SHOPPING_CATEGORIES,
  asShoppingCategory,
  categorizeIngredient,
} from "../src/index";

describe("asShoppingCategory", () => {
  it("accepts every canonical category", () => {
    for (const c of SHOPPING_CATEGORIES) {
      expect(asShoppingCategory(c)).toBe(c);
    }
  });

  it("rejects unknown strings and non-strings", () => {
    expect(asShoppingCategory("aisle 9")).toBeNull();
    expect(asShoppingCategory("Produce")).toBeNull(); // case-sensitive ids
    expect(asShoppingCategory(42)).toBeNull();
    expect(asShoppingCategory(null)).toBeNull();
    expect(asShoppingCategory(undefined)).toBeNull();
  });
});

describe("categorizeIngredient", () => {
  it("classifies common staples", () => {
    expect(categorizeIngredient("onion")).toBe("produce");
    expect(categorizeIngredient("chicken")).toBe("meat");
    expect(categorizeIngredient("milk")).toBe("dairy");
    expect(categorizeIngredient("flour")).toBe("pantry");
    expect(categorizeIngredient("ice cream")).toBe("frozen");
  });

  it("matches the head noun inside a longer name", () => {
    expect(categorizeIngredient("boneless skinless chicken thighs")).toBe("meat");
    expect(categorizeIngredient("large red onion")).toBe("produce");
    expect(categorizeIngredient("shredded cheddar cheese")).toBe("dairy");
    expect(categorizeIngredient("extra-virgin olive oil")).toBe("pantry");
  });

  it("lets exact phrases beat misleading words", () => {
    expect(categorizeIngredient("tomato")).toBe("produce");
    expect(categorizeIngredient("tomato paste")).toBe("pantry");
    expect(categorizeIngredient("coconut milk")).toBe("pantry");
    expect(categorizeIngredient("frozen peas")).toBe("frozen");
  });

  it("routes processed forms by modifier, beating the head noun", () => {
    expect(categorizeIngredient("can of fire roasted tomatoes")).toBe("pantry");
    expect(categorizeIngredient("canned chickpeas")).toBe("pantry");
    expect(categorizeIngredient("jarred roasted peppers")).toBe("pantry");
    expect(categorizeIngredient("dried apricots")).toBe("pantry");
    expect(categorizeIngredient("frozen mango chunks")).toBe("frozen");
  });

  it("folds simple plurals onto singular word entries", () => {
    expect(categorizeIngredient("shrimps")).toBe("meat"); // unlisted plural
    expect(categorizeIngredient("steaks")).toBe("meat");
    expect(categorizeIngredient("zucchinis")).toBe("produce");
  });

  it("is case- and whitespace-insensitive", () => {
    expect(categorizeIngredient("  Garlic ")).toBe("produce");
  });

  it("returns null for unknown ingredients and empty names", () => {
    expect(categorizeIngredient("xanthan gum")).toBeNull();
    expect(categorizeIngredient("")).toBeNull();
  });
});
