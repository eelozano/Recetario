import { useCallback, useEffect, useMemo, useState } from "react";
import { MealType, type MealEvent, type Recipe } from "@recetario/core";
import { getRepos } from "../data/repos";
import { AddMealDialog } from "../components/AddMealDialog";
import { loadWeekPlan, profileToStrings, type WeekPlan } from "../data/queries";
import { formatAmount, formatQuantity, macroUnit } from "../api/format";
import { MEAL_TYPES, MEAL_LABEL } from "../api/meal-types";
import { addDays, isoDate, startOfWeek } from "../api/week";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  /** Bump to force a reload (e.g. after a recipe is finalized elsewhere). */
  reloadKey?: number;
  /** Open a recipe's detail view (clicking a meal chip's title), see #70. */
  onOpenRecipe?: (recipeId: string) => void;
}

/**
 * Weekly meal calendar: schedule recipes into meal slots across a 7-day grid and
 * see per-day and whole-week macro rollups. A "week" is just a date range query.
 */
export function WeekCalendar({ reloadKey, onOpenRecipe }: Props) {
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
                      <div key={e.id} className="meal-chip">
                        <button
                          className="meal-chip__open"
                          title={`Open ${e.recipeTitle ?? "recipe"}`}
                          onClick={() => onOpenRecipe?.(e.recipeId)}
                        >
                          <span className="meal-chip__title">{e.recipeTitle ?? "Recipe"}</span>
                          <span className="meal-chip__servings">
                            ×{formatQuantity(e.servingsPlanned?.toString())}
                          </span>
                        </button>
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
          presetDate={adding.date}
          presetMealType={adding.mealType}
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
