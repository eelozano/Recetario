/**
 * Schedule a recipe into a meal slot (#32, #67, #70).
 *
 * Two entry points share this dialog:
 *  - From a calendar slot: the date + meal are fixed (the slot the user clicked),
 *    and they pick the recipe via the searchable combobox.
 *  - From a recipe's detail page (#70): the recipe is fixed, and they pick the
 *    date + meal — defaulting to today and the next still-empty slot.
 *
 * A field is rendered as a picker only when it isn't preset, so each entry point
 * shows exactly the choices it still needs.
 */
import { useEffect, useMemo, useState } from "react";
import { Decimal } from "decimal.js";
import { MealType, type Recipe } from "@recetario/core";

import { getRepos } from "../data/repos";
import { filterRecipes } from "../api/recipe-search";
import { MEAL_TYPES, MEAL_LABEL } from "../api/meal-types";
import { isoDate } from "../api/week";

interface Props {
  /** Recipe options for the combobox (ignored when `presetRecipe` is set). */
  recipes?: Recipe[];
  /** Fix the recipe (detail-page entry); hides the recipe picker. */
  presetRecipe?: Recipe;
  /** Fix the date (calendar-slot entry); hides the date picker. */
  presetDate?: string;
  /** Fix the meal slot (calendar-slot entry); hides the meal picker. */
  presetMealType?: MealType;
  onClose: () => void;
  onAdded: () => void;
}

export function AddMealDialog({
  recipes = [],
  presetRecipe,
  presetDate,
  presetMealType,
  onClose,
  onAdded,
}: Props) {
  const today = useMemo(() => isoDate(new Date()), []);
  const [recipeId, setRecipeId] = useState(presetRecipe?.id ?? "");
  const [date, setDate] = useState(presetDate ?? today);
  const [mealType, setMealType] = useState<MealType>(presetMealType ?? MealType.BREAKFAST);
  const [servings, setServings] = useState("1");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickDate = presetDate == null;
  const pickMeal = presetMealType == null;

  // When the user can choose the slot (detail-page entry), default to the next
  // still-empty meal on the chosen date — the slot they most likely want.
  useEffect(() => {
    if (!pickMeal) return;
    let active = true;
    (async () => {
      try {
        const { meals } = await getRepos();
        const onDay = await meals.listRange(date, date);
        if (!active) return;
        const taken = new Set(onDay.map((e) => e.mealType));
        const next = MEAL_TYPES.find((mt) => !taken.has(mt)) ?? MealType.BREAKFAST;
        setMealType(next);
      } catch {
        /* non-fatal: keep the current selection */
      }
    })();
    return () => {
      active = false;
    };
  }, [date, pickMeal]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (recipeId === "" || saving) return;
    setSaving(true);
    setError(null);
    let servingsPlanned: Decimal;
    try {
      servingsPlanned = new Decimal(servings || "1");
    } catch {
      servingsPlanned = new Decimal(1);
    }
    try {
      const { meals } = await getRepos();
      await meals.create({ date, mealType, recipeId, servingsPlanned });
      onAdded();
    } catch {
      setError("Could not schedule this meal.");
    } finally {
      setSaving(false);
    }
  }

  const prettyDate = new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  // The header names whatever's already fixed; what's left becomes a field.
  const title = presetRecipe
    ? `Add “${presetRecipe.title}” to plan`
    : `Add ${MEAL_LABEL[mealType]} — `;

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 className="modal__title">
          {title}
          {!presetRecipe && <span className="muted">{prettyDate}</span>}
        </h2>

        {!presetRecipe && recipes.length === 0 ? (
          <p className="muted">No recipes yet. Create one first.</p>
        ) : (
          <>
            {!presetRecipe && (
              <div className="modal__field">
                <span>Recipe</span>
                <RecipeCombobox recipes={recipes} onChange={setRecipeId} />
              </div>
            )}

            {pickDate && (
              <label className="modal__field">
                <span>Date</span>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value || today)}
                />
              </label>
            )}

            {pickMeal && (
              <label className="modal__field">
                <span>Meal</span>
                <select
                  value={mealType}
                  onChange={(e) => setMealType(e.target.value as MealType)}
                >
                  {MEAL_TYPES.map((mt) => (
                    <option key={mt} value={mt}>
                      {MEAL_LABEL[mt]}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="modal__field">
              <span>Servings</span>
              <input
                type="number"
                min="0.25"
                step="0.25"
                value={servings}
                onChange={(e) => setServings(e.target.value)}
              />
            </label>
          </>
        )}

        {error && <p className="error">{error}</p>}

        <div className="modal__actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn--accent"
            disabled={saving || recipeId === ""}
          >
            {saving ? "Adding…" : "Add to plan"}
          </button>
        </div>
      </form>
    </div>
  );
}

/**
 * Searchable recipe picker for the add-meal dialog (#67): type to filter by
 * title/tags, arrow keys + Enter or click to choose. Dependency-free; shares
 * its matching with the sidebar search. Reports the chosen recipe id ("" while
 * nothing is selected — typing clears any prior choice so a stale id can't be
 * submitted under an edited query).
 */
function RecipeCombobox({
  recipes,
  onChange,
}: {
  recipes: Recipe[];
  onChange: (recipeId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const matches = useMemo(() => filterRecipes(recipes, query), [recipes, query]);

  function select(r: Recipe) {
    onChange(r.id ?? "");
    setQuery(r.title);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && open && matches[highlight]) {
      e.preventDefault(); // choose, don't submit the form
      select(matches[highlight]);
    } else if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
    }
  }

  return (
    <div className="combobox">
      <input
        autoFocus
        type="text"
        placeholder="Search recipes…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setHighlight(0);
          setOpen(true);
          onChange("");
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {open && (
        // preventDefault on mousedown keeps the input focused, so blur doesn't
        // close the list before an option's click lands.
        <ul className="combobox__list" onMouseDown={(e) => e.preventDefault()}>
          {matches.length === 0 ? (
            <li className="combobox__empty muted">No recipes match</li>
          ) : (
            matches.map((r, i) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={`combobox__option ${i === highlight ? "is-active" : ""}`}
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => select(r)}
                >
                  {r.title}
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
