/** Recipe ⇆ Markdown serialization: round-trip, file format, best-effort parse. */
import { describe, it, expect } from "vitest";
import { Decimal } from "decimal.js";

import {
  recipeFromMarkdown,
  recipeToMarkdown,
  RecipeStatus,
  SourceType,
  type Recipe,
} from "../src/index";

function sampleRecipe(): Recipe {
  return {
    id: "0b9c8d7e-1f2a-4b3c-8d9e-0a1b2c3d4e5f",
    title: "Simple Garlic Soup",
    status: RecipeStatus.DRAFT,
    sourceType: SourceType.WEB,
    sourceUrl: "https://example.com/soup",
    servings: 4,
    tags: [{ name: "soup" }, { name: "quick" }],
    caloriesPerServing: new Decimal("90"),
    proteinPerServing: new Decimal("2"),
    sodiumPerServing: new Decimal("480"),
    ingredients: [
      {
        ingredient: { name: "garlic", normalizedName: "garlic" },
        rawText: "2 cloves garlic",
        quantity: new Decimal("2"),
        unit: "clove",
        category: "produce",
        position: 0,
      },
    ],
    instructionsMd: "Sauté the garlic in the oil.\n\nAdd water and simmer.",
    createdAt: "2026-06-07T12:00:00.000Z",
    updatedAt: "2026-06-07T12:00:00.000Z",
  };
}

describe("recipe serialization", () => {
  it("round-trips a recipe through markdown", () => {
    const parsed = recipeFromMarkdown(recipeToMarkdown(sampleRecipe()));

    expect(parsed.id).toBe("0b9c8d7e-1f2a-4b3c-8d9e-0a1b2c3d4e5f");
    expect(parsed.title).toBe("Simple Garlic Soup");
    expect(parsed.status).toBe(RecipeStatus.DRAFT);
    expect(parsed.sourceType).toBe(SourceType.WEB);
    expect(parsed.sourceUrl).toBe("https://example.com/soup");
    expect(parsed.servings).toBe(4);
    expect(parsed.tags?.map((t) => t.name)).toEqual(["soup", "quick"]);
    expect(parsed.caloriesPerServing?.toString()).toBe("90");
    expect(parsed.proteinPerServing?.toString()).toBe("2");
    expect(parsed.sodiumPerServing?.toString()).toBe("480");
    // Macros not published stay null.
    expect(parsed.fatPerServing).toBeNull();
    expect(parsed.ingredients).toHaveLength(1);
    expect(parsed.ingredients![0].ingredient.name).toBe("garlic");
    expect(parsed.ingredients![0].ingredient.normalizedName).toBe("garlic");
    expect(parsed.ingredients![0].quantity?.toString()).toBe("2");
    expect(parsed.ingredients![0].unit).toBe("clove");
    expect(parsed.ingredients![0].category).toBe("produce");
    expect(parsed.instructionsMd).toBe(
      "Sauté the garlic in the oil.\n\nAdd water and simmer.",
    );
  });

  it("writes frontmatter + markdown body in the agreed shape", () => {
    const md = recipeToMarkdown(sampleRecipe());
    expect(md.startsWith("---\n")).toBe(true);
    expect(md).toContain("title: Simple Garlic Soup");
    expect(md).toContain("macros_per_serving:");
    // Macros are plain numbers, not quoted strings.
    expect(md).toMatch(/calories: 90\b/);
    expect(md).not.toMatch(/calories: ['"]90['"]/);
    // Instructions live in the body, after the closing fence.
    expect(md).toContain("---\n\nSauté the garlic in the oil.");
  });

  it("omits null/empty fields from the file", () => {
    const md = recipeToMarkdown(sampleRecipe());
    expect(md).not.toContain("rating:");
    expect(md).not.toContain("description:");
    expect(md).not.toContain("fat:"); // unpublished macro absent, not `fat: null`
  });

  it("best-effort parses a sparse hand-written file without throwing", () => {
    const parsed = recipeFromMarkdown(
      ["---", "title: Quick Toast", "ingredients:", "  - name: bread", "---", "Toast it."].join(
        "\n",
      ),
    );
    expect(parsed.title).toBe("Quick Toast");
    expect(parsed.status).toBe(RecipeStatus.DRAFT); // defaulted
    expect(parsed.servings).toBeUndefined();
    expect(parsed.caloriesPerServing).toBeNull();
    expect(parsed.ingredients?.[0].ingredient.name).toBe("bread");
    expect(parsed.instructionsMd).toBe("Toast it.");
  });

  it("drops an unknown ingredient category instead of propagating it", () => {
    const parsed = recipeFromMarkdown(
      [
        "---",
        "title: Quick Toast",
        "ingredients:",
        "  - name: bread",
        "    category: aisle 9",
        "---",
      ].join("\n"),
    );
    expect(parsed.ingredients?.[0].category).toBeUndefined();
  });

  it("survives garbled frontmatter and missing fences", () => {
    expect(() => recipeFromMarkdown(": : not : valid : yaml :")).not.toThrow();
    const noFence = recipeFromMarkdown("Just some loose text, no frontmatter.");
    expect(noFence.title).toBe("Untitled recipe");
    expect(noFence.instructionsMd).toBe("Just some loose text, no frontmatter.");
  });
});
