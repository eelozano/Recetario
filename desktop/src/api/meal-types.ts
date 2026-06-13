/** Shared meal-slot constants for the calendar and the add-to-plan dialog. */
import { MealType } from "@recetario/core";

/** Slot order top-to-bottom in a calendar day and in pickers. */
export const MEAL_TYPES: MealType[] = [
  MealType.BREAKFAST,
  MealType.LUNCH,
  MealType.DINNER,
  MealType.SNACK,
];

export const MEAL_LABEL: Record<MealType, string> = {
  [MealType.BREAKFAST]: "Breakfast",
  [MealType.LUNCH]: "Lunch",
  [MealType.DINNER]: "Dinner",
  [MealType.SNACK]: "Snack",
};
