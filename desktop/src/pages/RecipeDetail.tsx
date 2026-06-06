import { useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { api, type MacroBreakdown, type RecipeOut } from "../api/client";
import type { paths } from "../api/schema";
import {
  formatAmount,
  formatQuantity,
  macroLabel,
  macroUnit,
  orderedMacroKeys,
} from "../api/format";

type IngredientLine = RecipeOut["ingredients"][number];
type RecipeUpdateBody = NonNullable<
  paths["/recipes/{recipe_id}"]["put"]["requestBody"]
>["content"]["application/json"];

/** Round-trip a loaded recipe back into the PUT body, applying field overrides. */
function toUpdateBody(
  recipe: RecipeOut,
  overrides: Partial<RecipeUpdateBody> = {},
): RecipeUpdateBody {
  return {
    title: recipe.title,
    description: recipe.description,
    source_url: recipe.source_url,
    source_type: recipe.source_type,
    servings: recipe.servings,
    rating: recipe.rating,
    status: recipe.status,
    instructions_md: recipe.instructions_md,
    ingredients: recipe.ingredients.map((l) => ({
      name: l.name,
      quantity: l.quantity,
      unit: l.unit,
      raw_text: l.raw_text,
      notes: l.notes,
      usda_fdc_id: l.usda_fdc_id,
      gram_weight: l.gram_weight,
    })),
    tags: recipe.tags.map((t) => t.name),
    ...overrides,
  };
}

interface Props {
  recipeId: number;
  /** Notify the parent when the recipe changes (e.g. finalized) to refresh lists. */
  onChanged?: () => void;
  /** Notify the parent after this recipe is deleted, so it can clear the selection. */
  onDeleted?: () => void;
}

/**
 * Recipe detail + the ingredient-level macro breakdown — the diagnostic view
 * that shows exactly which ingredient drives each macro. For imported drafts it
 * also offers the review → finalize step.
 */
export function RecipeDetail({ recipeId, onChanged, onDeleted }: Props) {
  const [recipe, setRecipe] = useState<RecipeOut | null>(null);
  const [macros, setMacros] = useState<MacroBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Bumped after a mutation (finalize) to reload this view in place.
  const [version, setVersion] = useState(0);
  const [finalizing, setFinalizing] = useState(false);
  // Two-step delete confirmation (window.confirm is unreliable in the webview).
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    setConfirmingDelete(false);
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
  }, [recipeId, version]);

  async function finalize() {
    if (!recipe || finalizing) return;
    setFinalizing(true);
    setError(null);
    const { error: apiError } = await api.PUT("/recipes/{recipe_id}", {
      params: { path: { recipe_id: recipe.id } },
      body: toUpdateBody(recipe, { status: "finalized" }),
    });
    setFinalizing(false);
    if (apiError) {
      setError("Could not finalize this recipe.");
      return;
    }
    setVersion((v) => v + 1);
    onChanged?.();
  }

  async function remove() {
    if (!recipe || deleting) return;
    setDeleting(true);
    setError(null);
    const { error: apiError } = await api.DELETE("/recipes/{recipe_id}", {
      params: { path: { recipe_id: recipe.id } },
    });
    if (apiError) {
      setDeleting(false);
      setConfirmingDelete(false);
      setError("Could not delete this recipe.");
      return;
    }
    onDeleted?.();
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error && !recipe) return <p className="error">{error}</p>;
  if (!recipe || !macros) return null;

  // Columns come from whichever macros the recipe actually accumulated.
  const columns = orderedMacroKeys(Object.keys(macros.totals));
  const isDraft = recipe.status === "draft";

  return (
    <div className="detail">
      <header className="detail__header">
        <div className="detail__titlebar">
          <h1>{recipe.title}</h1>
          <div className="detail__actions">
            {confirmingDelete ? (
              <>
                <button className="btn btn--danger" onClick={remove} disabled={deleting}>
                  {deleting ? "Deleting…" : "Confirm delete"}
                </button>
                <button
                  className="btn"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                className="btn"
                onClick={() => setConfirmingDelete(true)}
                title="Delete this recipe"
              >
                Delete
              </button>
            )}
          </div>
        </div>
        {error && recipe && <p className="error">{error}</p>}
        <div className="detail__meta">
          <span className={`pill pill--${recipe.status}`}>{recipe.status}</span>
          {recipe.servings != null && <span className="muted">{recipe.servings} servings</span>}
          {recipe.source_url && (
            // In the Tauri webview a plain target="_blank" link is a no-op — the
            // shell intercepts navigation. Hand the URL to the system browser via
            // the opener plugin. The href is kept for hover/right-click affordance.
            <a
              className="detail__source"
              href={recipe.source_url}
              onClick={(e) => {
                e.preventDefault();
                void openUrl(recipe.source_url!);
              }}
            >
              source ↗
            </a>
          )}
          {macros.unresolved_count > 0 && (
            <span className="pill pill--warn">
              {macros.unresolved_count} ingredient
              {macros.unresolved_count > 1 ? "s" : ""} unlinked
            </span>
          )}
        </div>
        {recipe.description && <p className="detail__desc">{recipe.description}</p>}
      </header>

      {isDraft && (
        <div className="draft-banner">
          <div>
            <strong>Imported draft</strong>
            <p className="muted">
              Review the ingredients and directions below
              {macros.unresolved_count > 0 && ", link any unmatched ingredients,"} then
              finalize to add it to your collection.
            </p>
          </div>
          <button className="btn btn--accent" onClick={finalize} disabled={finalizing}>
            {finalizing ? "Finalizing…" : "Finalize recipe"}
          </button>
        </div>
      )}

      {/* Primary cooking content first; macros are secondary planning info, so
          the totals cards and the per-ingredient breakdown are grouped below. */}
      <IngredientList ingredients={recipe.ingredients} />

      <Directions instructionsMd={recipe.instructions_md} />

      <SummaryCards macros={macros} columns={columns} />

      <section>
        <h2 className="section-title">Per-ingredient breakdown</h2>
        {columns.length === 0 ? (
          <p className="muted">
            No macros yet — link ingredients to USDA foods to populate this view.
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
