/**
 * Recipe ⇆ Markdown serialization.
 *
 * A recipe is stored as a single `.md` file: a YAML frontmatter block (metadata,
 * ingredients, per-serving macros) followed by the instructions as the Markdown
 * body. Keys are snake_case (idiomatic, hand-edit friendly); null/empty fields
 * are omitted on write to keep files clean.
 *
 * Reading is **best-effort**: a missing or garbled field falls back to a safe
 * default and never throws, so a hand-edited file can't crash the app.
 */
import { Decimal } from "decimal.js";
import yaml from "js-yaml";

import {
  type Ingredient,
  type Recipe,
  type RecipeIngredient,
  RecipeStatus,
  SourceType,
  type Tag,
} from "../entities/recipe";
import { normalizeIngredientName } from "./normalize";

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

// --- write -----------------------------------------------------------------

/** A Decimal as a plain YAML number (re-parsed exactly via `new Decimal(String(n))`). */
function num(value: Decimal | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  return Number(value.toString());
}

function ingredientToData(line: RecipeIngredient): Record<string, unknown> {
  const out: Record<string, unknown> = { name: line.ingredient.name };
  if (line.rawText) out.raw_text = line.rawText;
  const quantity = num(line.quantity);
  if (quantity !== undefined) out.quantity = quantity;
  if (line.unit) out.unit = line.unit;
  if (line.usdaFdcId !== null && line.usdaFdcId !== undefined) {
    out.usda_fdc_id = line.usdaFdcId;
  }
  const gramWeight = num(line.gramWeight);
  if (gramWeight !== undefined) out.gram_weight = gramWeight;
  if (line.notes) out.notes = line.notes;
  return out;
}

const MACRO_FIELDS: ReadonlyArray<[keyof Recipe, string]> = [
  ["caloriesPerServing", "calories"],
  ["proteinPerServing", "protein"],
  ["fatPerServing", "fat"],
  ["carbsPerServing", "carbohydrate"],
  ["fiberPerServing", "fiber"],
  ["sodiumPerServing", "sodium"],
];

export function recipeToMarkdown(recipe: Recipe): string {
  const data: Record<string, unknown> = {};

  if (recipe.id) data.id = recipe.id;
  data.title = recipe.title;
  data.status = recipe.status ?? RecipeStatus.DRAFT;
  if (recipe.description) data.description = recipe.description;

  const source: Record<string, unknown> = {};
  if (recipe.sourceType) source.type = recipe.sourceType;
  if (recipe.sourceUrl) source.url = recipe.sourceUrl;
  if (Object.keys(source).length > 0) data.source = source;

  if (recipe.servings !== null && recipe.servings !== undefined) {
    data.servings = recipe.servings;
  }
  if (recipe.rating !== null && recipe.rating !== undefined) {
    data.rating = recipe.rating;
  }
  if (recipe.tags && recipe.tags.length > 0) {
    data.tags = recipe.tags.map((t) => t.name);
  }

  const macros: Record<string, number> = {};
  for (const [field, key] of MACRO_FIELDS) {
    const value = num(recipe[field] as Decimal | null | undefined);
    if (value !== undefined) macros[key] = value;
  }
  if (Object.keys(macros).length > 0) data.macros_per_serving = macros;

  if (recipe.ingredients && recipe.ingredients.length > 0) {
    data.ingredients = recipe.ingredients.map(ingredientToData);
  }

  if (recipe.createdAt) data.created_at = recipe.createdAt;
  if (recipe.updatedAt) data.updated_at = recipe.updatedAt;

  const frontmatter = yaml.dump(data, { lineWidth: -1, sortKeys: false });
  const body = (recipe.instructionsMd ?? "").trim();
  return `---\n${frontmatter}---\n${body ? `\n${body}\n` : ""}`;
}

// --- read (best-effort) ----------------------------------------------------

function asString(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return undefined;
}

function asInt(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return Math.trunc(n);
  }
  return undefined;
}

function asDecimal(value: unknown): Decimal | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value !== "number" && typeof value !== "string") return undefined;
  try {
    return new Decimal(String(value));
  } catch {
    return undefined;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function sourceTypeOf(value: unknown): SourceType | undefined {
  const s = asString(value);
  return s !== undefined && (Object.values(SourceType) as string[]).includes(s)
    ? (s as SourceType)
    : undefined;
}

function statusOf(value: unknown): RecipeStatus {
  const s = asString(value);
  return s !== undefined && (Object.values(RecipeStatus) as string[]).includes(s)
    ? (s as RecipeStatus)
    : RecipeStatus.DRAFT;
}

function ingredientFromData(value: unknown, position: number): RecipeIngredient | null {
  const row = asRecord(value);
  const name = asString(row.name);
  if (name === undefined || name.trim() === "") return null;

  const ingredient: Ingredient = {
    name,
    normalizedName: normalizeIngredientName(name),
    usdaFdcId: asInt(row.usda_fdc_id) ?? null,
  };
  const line: RecipeIngredient = { ingredient, position };

  const rawText = asString(row.raw_text);
  if (rawText !== undefined) line.rawText = rawText;
  const quantity = asDecimal(row.quantity);
  if (quantity !== undefined) line.quantity = quantity;
  const unit = asString(row.unit);
  if (unit !== undefined) line.unit = unit;
  const fdc = asInt(row.usda_fdc_id);
  if (fdc !== undefined) line.usdaFdcId = fdc;
  const gramWeight = asDecimal(row.gram_weight);
  if (gramWeight !== undefined) line.gramWeight = gramWeight;
  const notes = asString(row.notes);
  if (notes !== undefined) line.notes = notes;

  return line;
}

export function recipeFromMarkdown(content: string): Recipe {
  const match = FRONTMATTER_RE.exec(content);
  let data: Record<string, unknown> = {};
  let body = content;
  if (match) {
    try {
      data = asRecord(yaml.load(match[1]));
    } catch {
      data = {};
    }
    body = match[2] ?? "";
  }

  const recipe: Recipe = {
    title: asString(data.title) ?? "Untitled recipe",
    status: statusOf(data.status),
  };

  const id = asString(data.id);
  if (id !== undefined) recipe.id = id;

  const description = asString(data.description);
  if (description !== undefined) recipe.description = description;

  const source = asRecord(data.source);
  const sourceType = sourceTypeOf(source.type);
  if (sourceType !== undefined) recipe.sourceType = sourceType;
  const sourceUrl = asString(source.url);
  if (sourceUrl !== undefined) recipe.sourceUrl = sourceUrl;

  const servings = asInt(data.servings);
  if (servings !== undefined) recipe.servings = servings;
  const rating = asInt(data.rating);
  if (rating !== undefined) recipe.rating = rating;

  if (Array.isArray(data.tags)) {
    const tags: Tag[] = [];
    for (const t of data.tags) {
      const name = asString(t);
      if (name !== undefined && name.trim() !== "") tags.push({ name });
    }
    if (tags.length > 0) recipe.tags = tags;
  }

  const macros = asRecord(data.macros_per_serving);
  recipe.caloriesPerServing = asDecimal(macros.calories) ?? null;
  recipe.proteinPerServing = asDecimal(macros.protein) ?? null;
  recipe.fatPerServing = asDecimal(macros.fat) ?? null;
  recipe.carbsPerServing = asDecimal(macros.carbohydrate) ?? null;
  recipe.fiberPerServing = asDecimal(macros.fiber) ?? null;
  recipe.sodiumPerServing = asDecimal(macros.sodium) ?? null;

  if (Array.isArray(data.ingredients)) {
    const lines: RecipeIngredient[] = [];
    data.ingredients.forEach((row, i) => {
      const line = ingredientFromData(row, i);
      if (line) lines.push(line);
    });
    recipe.ingredients = lines;
  }

  const instructions = body.trim();
  if (instructions !== "") recipe.instructionsMd = instructions;

  const createdAt = asString(data.created_at);
  if (createdAt !== undefined) recipe.createdAt = createdAt;
  const updatedAt = asString(data.updated_at);
  if (updatedAt !== undefined) recipe.updatedAt = updatedAt;

  return recipe;
}
