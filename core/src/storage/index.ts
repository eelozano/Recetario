/**
 * Pure storage surface (no `node:fs`). The Node adapter is intentionally NOT
 * re-exported here — import it from `@recetario/core/node` instead.
 */
export type { FileSystem } from "./fs";
export { joinPath, dirOf, atomicWrite } from "./fs";
export { newId } from "./id";
export { normalizeIngredientName } from "./normalize";
export {
  RECIPES_DIR,
  slug,
  short8,
  recipeFileName,
  recipeFileSuffix,
} from "./recipe-layout";
export { recipeToMarkdown, recipeFromMarkdown } from "./recipe-serialization";
export { RecipeRepository } from "./recipe-repository";
export {
  CONFLICT_SUFFIX_RE,
  scanRecipeConflicts,
  resolveRecipeConflict,
} from "./conflicts";
export type { ConflictFile, ConflictGroup, ConflictReason } from "./conflicts";

export { monthFileToString, eventsFromMonthFile } from "./meal-serialization";
export { MealEventRepository, MEAL_DIR } from "./meal-repository";

export { shoppingListToYaml, shoppingListFromYaml } from "./shopping-serialization";
export { ShoppingListRepository, SHOPPING_DIR } from "./shopping-repository";

export {
  CategoryOverridesStore,
  CATEGORY_OVERRIDES_FILE,
} from "./category-overrides";

export {
  CustomCategoriesStore,
  CUSTOM_CATEGORIES_FILE,
  customCategoryId,
} from "./custom-categories";
export type { CustomCategory } from "./custom-categories";
