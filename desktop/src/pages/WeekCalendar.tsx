import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type MealEvent,
  type MealType,
  type RecipeSummary,
  type WeekPlan,
} from "../api/client";
import { formatAmount, formatQuantity, macroUnit } from "../api/format";
import { addDays, isoDate, startOfWeek } from "../api/week";

const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "dinner", "snack"];
const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
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
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<{ date: string; mealType: MealType } | null>(null);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );
  const start = isoDate(days[0]);
  const end = isoDate(days[6]);

  const loadPlan = useCallback(async () => {
    const { data, error: apiError } = await api.GET("/meals", {
      params: { query: { start, end } },
    });
    if (apiError || !data) {
      setError("Could not load the meal plan. Is the API running?");
      return;
    }
    setError(null);
    setPlan(data);
  }, [start, end]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan, reloadKey]);

  // Recipe options for the scheduler — only finalized recipes are worth planning.
  useEffect(() => {
    (async () => {
      const { data } = await api.GET("/recipes", { params: { query: {} } });
      if (data) setRecipes(data);
    })();
  }, [reloadKey]);

  // Index events by "date|mealType" and per-day calorie totals for quick lookup.
  const eventsByCell = useMemo(() => {
    const map = new Map<string, MealEvent[]>();
    for (const e of plan?.events ?? []) {
      const key = `${e.date}|${e.meal_type}`;
      const bucket = map.get(key);
      if (bucket) bucket.push(e);
      else map.set(key, [e]);
    }
    return map;
  }, [plan]);

  const caloriesByDay = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of plan?.macros.days ?? []) {
      if (d.totals.calories != null) map.set(d.date, d.totals.calories);
    }
    return map;
  }, [plan]);

  async function deleteEvent(id: number) {
    const { error: apiError } = await api.DELETE("/meals/{event_id}", {
      params: { path: { event_id: id } },
    });
    if (!apiError) loadPlan();
  }

  const weekLabel = `${days[0].toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })} – ${days[6].toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;

  const weekTotals = plan?.macros.totals ?? {};

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
                      <div key={e.id} className="meal-chip" title={e.recipe_title ?? ""}>
                        <span className="meal-chip__title">{e.recipe_title ?? "Recipe"}</span>
                        <span className="meal-chip__servings">
                          ×{formatQuantity(e.servings_planned)}
                        </span>
                        <button
                          className="meal-chip__remove"
                          title="Remove"
                          onClick={() => deleteEvent(e.id)}
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
  recipes: RecipeSummary[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [recipeId, setRecipeId] = useState<number | "">(recipes[0]?.id ?? "");
  const [servings, setServings] = useState("1");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (recipeId === "" || saving) return;
    setSaving(true);
    setError(null);
    const { error: apiError } = await api.POST("/meals", {
      body: {
        date,
        meal_type: mealType,
        recipe_id: Number(recipeId),
        servings_planned: servings || "1",
      },
    });
    setSaving(false);
    if (apiError) {
      setError("Could not schedule this meal.");
      return;
    }
    onAdded();
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
          <p className="muted">No recipes yet. Create or import one first.</p>
        ) : (
          <>
            <label className="modal__field">
              <span>Recipe</span>
              <select
                value={recipeId}
                onChange={(e) => setRecipeId(e.target.value ? Number(e.target.value) : "")}
              >
                {recipes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                  </option>
                ))}
              </select>
            </label>
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
