/**
 * Recipe-domain entities. Port of `domain/entities/recipe.py`.
 *
 * Pure in-memory shapes the business logic operates on — no ORM, no I/O. Fields
 * that carry defaults in the Python dataclasses are optional here; the storage
 * layer (a later step) is responsible for supplying them on read.
 *
 * Identity is a UUID string (`Id`) — see ../identity.ts. `usdaFdcId` is the one
 * exception: it's an external USDA FoodData Central integer, not our identity.
 */
import type { Decimal } from "decimal.js";

import type { Id } from "../identity";

export enum SourceType {
  WEB = "web",
  VIDEO = "video",
  MANUAL = "manual",
}

export enum RecipeStatus {
  DRAFT = "draft",
  FINALIZED = "finalized",
}

export interface Tag {
  name: string;
  id?: Id | null;
}

/** A canonical, deduplicated ingredient in the user's catalog. */
export interface Ingredient {
  name: string;
  normalizedName: string;
  id?: Id | null;
  usdaFdcId?: number | null;
  defaultUnit?: string | null;
}

/**
 * A single ingredient line on a recipe — the ingredient-level macro link.
 * `usdaFdcId` and `gramWeight` are populated by nutrition resolution and drive
 * per-ingredient macro math.
 */
export interface RecipeIngredient {
  ingredient: Ingredient;
  quantity?: Decimal | null;
  unit?: string | null;
  rawText?: string | null;
  position?: number;
  usdaFdcId?: number | null;
  gramWeight?: Decimal | null;
  notes?: string | null;
  id?: Id | null;
}

export interface Recipe {
  title: string;
  id?: Id | null;
  description?: string | null;
  sourceUrl?: string | null;
  sourceType?: SourceType;
  servings?: number | null;
  rating?: number | null;
  status?: RecipeStatus;
  instructionsMd?: string | null;
  /**
   * Recipe-level macros, entered by hand per serving. These are the primary
   * macro source: when any is set, the MacroCalculator uses them directly
   * instead of summing ingredient-level USDA links.
   */
  caloriesPerServing?: Decimal | null;
  proteinPerServing?: Decimal | null;
  fatPerServing?: Decimal | null;
  carbsPerServing?: Decimal | null;
  fiberPerServing?: Decimal | null;
  sodiumPerServing?: Decimal | null;
  ingredients?: RecipeIngredient[];
  tags?: Tag[];
  createdAt?: string | null;
  updatedAt?: string | null;
}
