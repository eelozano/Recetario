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
