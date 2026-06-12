/**
 * Recipe search/filtering shared by the sidebar list and the calendar's
 * add-meal combobox (#67). Plain case-insensitive matching — every
 * whitespace-separated term must appear somewhere in the title or a tag, so
 * "chicken soup" finds "Soup, chicken" and tag searches like "dinner quick"
 * work. In-memory only: recipes are already fully loaded client-side.
 */
import type { Recipe } from "@recetario/core";

export function recipeMatches(recipe: Recipe, query: string): boolean {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const title = recipe.title.toLowerCase();
  const tags = (recipe.tags ?? []).map((t) => t.name.toLowerCase());
  return terms.every(
    (term) => title.includes(term) || tags.some((tag) => tag.includes(term)),
  );
}

export function filterRecipes(recipes: Recipe[], query: string): Recipe[] {
  if (!query.trim()) return recipes;
  return recipes.filter((r) => recipeMatches(r, query));
}
