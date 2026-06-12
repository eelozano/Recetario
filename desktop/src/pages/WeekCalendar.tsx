import { useCallback, useEffect, useMemo, useState } from "react";
import { Decimal } from "decimal.js";
import { MealType, type MealEvent, type Recipe } from "@recetario/core";
import { getRepos } from "../data/repos";
import { filterRecipes } from "../api/recipe-search";
import { loadWeekPlan, profileToStrings, type WeekPlan } from "../data/queries";
import { formatAmount, formatQuantity, macroUnit } from "../api/format";
import { addDays, isoDate, startOfWeek } from "../api/week";

const MEAL_TYPES: MealType[] = [
  MealType.BREAKFAST,
  MealType.LUNCH,
  MealType.DINNER,
  MealType.SNACK,
];
const MEAL_LABEL: Record<MealType, string> = {
  [MealType.BREAKFAST]: "Breakfast",
  [MealType.LUNCH]: "Lunch",
  [MealType.DINNER]: "Dinner",
  [MealType.SNACK]: "Snack",
};
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  /** Bump to force a reload (e.g. after a recipe is finalized elsewhere). */
  reloadKey?: number;
}

/**
 * Weekly meal calendar: schedule recipes into meal slots across a 7-day grid and
 * see per-day and whole-week macro rollups. A "week" is just a date range query.
 */
export function WeekCalendar({ reloadKey }: Props) {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [plan, setPlan] = useState<WeekPlan | null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<{ date: string; mealType: MealType } | null>(null);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );
  const start = isoDate(days[0]);
  const end = isoDate(days[6]);

  const loadPlan = useCallback(async () => {
    try {
      setError(null);
      setPlan(await loadWeekPlan(start, end));
    } catch {
      setError("Could not load the meal plan.");
    }
  }, [start, end]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan, reloadKey]);

  // Recipe options for the scheduler.
  useEffect(() => {
    (async () => {
      try {
        const { recipes } = await getRepos();
        const data = await recipes.list();
        data.sort((a, b) => a.title.toLowerCase().localeCompare(b.title.toLowerCase()));
        setRecipes(data);
      } catch {
        // Non-fatal: the scheduler simply shows no recipe options.
      }
    })();
  }, [reloadKey]);

  // Index events by "date|mealType" and per-day calorie totals for quick lookup.
  const eventsByCell = useMemo(() => {
    const map = new Map<string, MealEvent[]>();
    for (const e of plan?.events ?? []) {
      const key = `${e.date}|${e.mealType}`;
      const bucket = map.get(key);
      if (bucket) bucket.push(e);
      else map.set(key, [e]);
    }
    return map;
  }, [plan]);

  const caloriesByDay = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of plan?.macros.days ?? []) {
      const cals = d.totals.amounts.calories;
      if (cals != null) map.set(d.date, cals.toString());
    }
    return map;
  }, [plan]);

  async function deleteEvent(id: string) {
    try {
      const { meals } = await getRepos();
      await meals.delete(id);
      loadPlan();
    } catch {
      setError("Could not remove this meal.");
    }
  }

  const weekLabel = `${days[0].toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })} – ${days[6].toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;

  const weekTotals = plan ? profileToStrings(plan.macros.totals) : {};

  return (
    <div className="calendar">
      <header className="calendar__header">
        <div className="calendar__nav">
          <button className="btn" onClick={() => setWeekStart(addDays(weekStart, -7))}>
            ‹ Prev
          </button>
          <button className="btn" onClick={() => setWeekStart(startOfWeek(new Date()))}>
            This week
          </button>
          <button className="btn" onClick={() => setWeekStart(addDays(weekStart, 7))}>
            Next ›
          </button>
        </div>
        <h1 className="calendar__title">{weekLabel}</h1>
        <WeekTotals totals={weekTotals} />
      </header>

      {error && <p className="error">{error}</p>}

      <div className="calendar__grid">
        {days.map((day, i) => {
          const dateStr = isoDate(day);
          const isToday = dateStr === isoDate(new Date());
          return (
            <div key={dateStr} className={`day ${isToday ? "day--today" : ""}`}>
              <div className="day__head">
                <span className="day__name">{DAY_LABELS[i]}</span>
                <span className="day__num">{day.getDate()}</span>
              </div>
              {MEAL_TYPES.map((mt) => {
                const cellEvents = eventsByCell.get(`${dateStr}|${mt}`) ?? [];
                return (
                  <div key={mt} className="slot">
                    <button
                      className="slot__label"
                      title={`Add ${MEAL_LABEL[mt]}`}
                      onClick={() => setAdding({ date: dateStr, mealType: mt })}
                    >
                      {MEAL_LABEL[mt]} <span className="slot__plus">+</span>
                    </button>
                    {cellEvents.map((e) => (
                      <div key={e.id} className="meal-chip" title={e.recipeTitle ?? ""}>
                        <span className="meal-chip__title">{e.recipeTitle ?? "Recipe"}</span>
                        <span className="meal-chip__servings">
                          ×{formatQuantity(e.servingsPlanned?.toString())}
                        </span>
                        <button
                          className="meal-chip__remove"
                          title="Remove"
                          onClick={() => deleteEvent(e.id!)}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                );
              })}
              <div className="day__total">
                {caloriesByDay.has(dateStr)
                  ? `${formatAmount(caloriesByDay.get(dateStr))} kcal`
                  : "—"}
              </div>
            </div>
          );
        })}
      </div>

      {adding && (
        <AddMealDialog
          date={adding.date}
          mealType={adding.mealType}
          recipes={recipes}
          onClose={() => setAdding(null)}
          onAdded={() => {
            setAdding(null);
            loadPlan();
          }}
        />
      )}
    </div>
  );
}

function WeekTotals({ totals }: { totals: Record<string, string> }) {
  const cals = totals.calories;
  const protein = totals.protein;
  if (cals == null && protein == null) {
    return <span className="calendar__totals muted">No macros yet</span>;
  }
  return (
    <span className="calendar__totals">
      {cals != null && (
        <strong>
          {formatAmount(cals)} <span className="unit">kcal</span>
        </strong>
      )}
      {protein != null && (
        <span className="muted">
          {" "}
          · {formatAmount(protein)} {macroUnit("protein")} protein
        </span>
      )}
      <span className="muted"> this week</span>
    </span>
  );
}

function AddMealDialog({
  date,
  mealType,
  recipes,
  onClose,
  onAdded,
}: {
  date: string;
  mealType: MealType;
  recipes: Recipe[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [recipeId, setRecipeId] = useState("");
  const [servings, setServings] = useState("1");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 className="modal__title">
          Add {MEAL_LABEL[mealType]} — <span className="muted">{prettyDate}</span>
        </h2>

        {recipes.length === 0 ? (
          <p className="muted">No recipes yet. Create one first.</p>
        ) : (
          <>
            <div className="modal__field">
              <span>Recipe</span>
              <RecipeCombobox recipes={recipes} onChange={setRecipeId} />
            </div>
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
