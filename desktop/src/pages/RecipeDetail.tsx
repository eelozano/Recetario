import { useEffect, useState } from "react";
import { api, type MacroBreakdown, type RecipeOut } from "../api/client";
import {
  formatAmount,
  formatQuantity,
  macroLabel,
  macroUnit,
  orderedMacroKeys,
} from "../api/format";

type IngredientLine = RecipeOut["ingredients"][number];

interface Props {
  recipeId: number;
}

/**
 * Recipe detail + the ingredient-level macro breakdown — the diagnostic view
 * that shows exactly which ingredient drives each macro.
 */
export function RecipeDetail({ recipeId }: Props) {
  const [recipe, setRecipe] = useState<RecipeOut | null>(null);
  const [macros, setMacros] = useState<MacroBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      const params = { params: { path: { recipe_id: recipeId } } };
      const [recipeRes, macroRes] = await Promise.all([
        api.GET("/recipes/{recipe_id}", params),
        api.GET("/recipes/{recipe_id}/macros", params),
      ]);
      if (!active) return;
      if (recipeRes.error || macroRes.error) {
        setError("Could not load this recipe");
      } else {
        setRecipe(recipeRes.data ?? null);
        setMacros(macroRes.data ?? null);
      }
      setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [recipeId]);

  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!recipe || !macros) return null;

  // Columns come from whichever macros the recipe actually accumulated.
  const columns = orderedMacroKeys(Object.keys(macros.totals));

  return (
    <div className="detail">
      <header className="detail__header">
        <h1>{recipe.title}</h1>
        <div className="detail__meta">
          <span className={`pill pill--${recipe.status}`}>{recipe.status}</span>
          {recipe.servings != null && <span className="muted">{recipe.servings} servings</span>}
          {macros.unresolved_count > 0 && (
            <span className="pill pill--warn">
              {macros.unresolved_count} ingredient
              {macros.unresolved_count > 1 ? "s" : ""} unlinked
            </span>
          )}
        </div>
        {recipe.description && <p className="detail__desc">{recipe.description}</p>}
      </header>

      <SummaryCards macros={macros} columns={columns} />

      <IngredientList ingredients={recipe.ingredients} />

      <Directions instructionsMd={recipe.instructions_md} />

      <section>
        <h2 className="section-title">Per-ingredient breakdown</h2>
        {columns.length === 0 ? (
          <p className="muted">
            No macros yet — link ingredients to USDA foods (POST
            <code> /recipes/{recipe.id}/ingredients/&#123;position&#125;/link</code>) to populate
            this view.
          </p>
        ) : (
          <table className="macro-table">
            <thead>
              <tr>
                <th className="left">Ingredient</th>
                <th>Grams</th>
                {columns.map((c) => (
                  <th key={c}>
                    {macroLabel(c)}
                    <span className="unit"> ({macroUnit(c)})</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {macros.lines.map((line, i) => (
                <tr key={line.recipe_ingredient_id ?? i} className={line.resolved ? "" : "is-unresolved"}>
                  <td className="left">
                    {line.ingredient_name}
                    {!line.resolved && <span className="tag tag--warn">not linked</span>}
                  </td>
                  <td>{line.gram_weight != null ? formatAmount(line.gram_weight) : "—"}</td>
                  {columns.map((c) => (
                    <td key={c}>{line.resolved ? formatAmount(line.macros[c]) : "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="left">Total</td>
                <td></td>
                {columns.map((c) => (
                  <td key={c}>
                    <strong>{formatAmount(macros.totals[c])}</strong>
                  </td>
                ))}
              </tr>
              {macros.per_serving && (
                <tr className="per-serving-row">
                  <td className="left">Per serving</td>
                  <td></td>
                  {columns.map((c) => (
                    <td key={c}>{formatAmount(macros.per_serving![c])}</td>
                  ))}
                </tr>
              )}
            </tfoot>
          </table>
        )}
      </section>
    </div>
  );
}

/** Compose a human-readable line: "3 pc Yellow onion (finely sliced)". */
function ingredientText(line: IngredientLine): string {
  const qty = formatQuantity(line.quantity);
  const parts = [qty, line.unit?.trim(), line.name?.trim()].filter(
    (p): p is string => Boolean(p && p.length),
  );
  let text = parts.join(" ").trim();
  // Fall back to the originally parsed string if we have nothing structured.
  if (!text) text = line.raw_text?.trim() ?? "";
  if (line.notes?.trim()) text += ` (${line.notes.trim()})`;
  return text;
}

function IngredientList({ ingredients }: { ingredients: IngredientLine[] }) {
  if (!ingredients.length) return null;
  const ordered = [...ingredients].sort((a, b) => a.position - b.position);
  return (
    <section>
      <h2 className="section-title">Ingredients</h2>
      <ul className="ingredient-list">
        {ordered.map((line, i) => (
          <li key={line.id ?? i}>{ingredientText(line)}</li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Render the directions markdown. We keep this dependency-free: numbered or
 * bulleted lines become an ordered list of steps; blank lines separate them.
 */
function Directions({ instructionsMd }: { instructionsMd: string | null }) {
  const steps = parseSteps(instructionsMd);
  if (!steps.length) return null;
  return (
    <section>
      <h2 className="section-title">Directions</h2>
      <ol className="directions">
        {steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
    </section>
  );
}

/** Split directions markdown into clean step strings (markers stripped). */
function parseSteps(md: string | null | undefined): string[] {
  if (!md) return [];
  return md
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length)
    // Strip leading "1." / "1)" / "-" / "*" / "#" markers.
    .map((l) => l.replace(/^(#{1,6}\s+|\d+[.)]\s+|[-*]\s+)/, "").trim())
    .filter((l) => l.length);
}

function SummaryCards({
  macros,
  columns,
}: {
  macros: MacroBreakdown;
  columns: string[];
}) {
  if (columns.length === 0) return null;
  return (
    <section className="cards">
      <MacroCard title="Recipe total" amounts={macros.totals} columns={columns} />
      {macros.per_serving && (
        <MacroCard title="Per serving" amounts={macros.per_serving} columns={columns} />
      )}
    </section>
  );
}

function MacroCard({
  title,
  amounts,
  columns,
}: {
  title: string;
  amounts: Record<string, string>;
  columns: string[];
}) {
  return (
    <div className="card">
      <div className="card__title">{title}</div>
      <div className="card__grid">
        {columns.map((c) => (
          <div key={c} className="card__stat">
            <span className="card__value">{formatAmount(amounts[c])}</span>
            <span className="card__label">
              {macroLabel(c)} <span className="unit">{macroUnit(c)}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
