/**
 * Typed client for the Recetario local API.
 *
 * Types in `schema.d.ts` are generated from the backend's OpenAPI document
 * (`npm run gen:api`), so this client stays in lockstep with the FastAPI
 * contract — the UI never hand-rolls request/response shapes.
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";

// The headless FastAPI runs on localhost (see backend Settings.api_port).
// Overridable at build time for the hosted/web deployment.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765";

export const api = createClient<paths>({ baseUrl: API_BASE_URL });

// Handy aliases for the response shapes the UI renders.
export type RecipeSummary =
  paths["/recipes"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type RecipeOut =
  paths["/recipes/{recipe_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type MacroBreakdown =
  paths["/recipes/{recipe_id}/macros"]["get"]["responses"]["200"]["content"]["application/json"];
export type LineMacro = MacroBreakdown["lines"][number];

// Ingestion (recipe import) job, as polled by the Import-from-URL UI.
export type IngestionJob =
  paths["/ingestion/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"];

// Meal calendar (Phase 4): a week's plan plus its macro rollups.
export type WeekPlan =
  paths["/meals"]["get"]["responses"]["200"]["content"]["application/json"];
export type MealEvent = WeekPlan["events"][number];
export type MealEventCreate =
  paths["/meals"]["post"]["requestBody"]["content"]["application/json"];
export type MealType = MealEvent["meal_type"];

// Shopping lists (Phase 5).
export type ShoppingListSummary =
  paths["/shopping-lists"]["get"]["responses"]["200"]["content"]["application/json"][number];
export type ShoppingList =
  paths["/shopping-lists/{list_id}"]["get"]["responses"]["200"]["content"]["application/json"];
export type ShoppingItem = ShoppingList["items"][number];
