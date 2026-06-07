import { Fragment, type FormEvent, useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  api,
  type FoodSummary,
  type MacroBreakdown,
  type RecipeOut,
} from "../api/client";
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
    calories_per_serving: recipe.calories_per_serving,
    protein_per_serving: recipe.protein_per_serving,
    fat_per_serving: recipe.fat_per_serving,
    carbs_per_serving: recipe.carbs_per_serving,
    fiber_per_serving: recipe.fiber_per_serving,
    sodium_per_serving: recipe.sodium_per_serving,
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
  // Whether the detail is in edit mode (the title/ingredients/instructions form).
  const [editing, setEditing] = useState(false);
  // Which ingredient position has its USDA-link panel open (null = none).
  const [linkingPosition, setLinkingPosition] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    setConfirmingDelete(false);
    setLinkingPosition(null);
    setEditing(false);
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

  // Reload recipe + macros in place after a link/unlink, and refresh the parent
  // list (the "unlinked" badge in the sidebar may change).
  function reload() {
    setVersion((v) => v + 1);
    onChanged?.();
  }

  // Unlink one line by PUTting the recipe with that line's USDA match cleared.
  async function unlink(position: number) {
    if (!recipe) return;
    setError(null);
    const body = toUpdateBody(recipe, {
      ingredients: recipe.ingredients.map((l) => ({
        name: l.name,
        quantity: l.quantity,
        unit: l.unit,
        raw_text: l.raw_text,
        notes: l.notes,
        usda_fdc_id: l.position === position ? null : l.usda_fdc_id,
        gram_weight: l.position === position ? null : l.gram_weight,
      })),
    });
    const { error: apiError } = await api.PUT("/recipes/{recipe_id}", {
      params: { path: { recipe_id: recipe.id } },
      body,
    });
    if (apiError) {
      setError("Could not unlink this ingredient.");
      return;
    }
    reload();
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error && !recipe) return <p className="error">{error}</p>;
  if (!recipe || !macros) return null;

  if (editing) {
    return (
      <RecipeEditForm
        recipe={recipe}
        onSaved={() => {
          setEditing(false);
          reload();
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }

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
              <>
                <button className="btn" onClick={() => setEditing(true)} title="Edit this recipe">
                  Edit
                </button>
                <button
                  className="btn"
                  onClick={() => setConfirmingDelete(true)}
                  title="Delete this recipe"
                >
                  Delete
                </button>
              </>
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

      <MacroEditor recipe={recipe} onSaved={reload} />

      <SummaryCards macros={macros} columns={columns} />

      {/* The per-ingredient USDA breakdown only applies when macros come from
          ingredient links. With hand-entered macros (#18) there are no lines, so
          this diagnostic table is hidden — the summary cards above carry the
          numbers. (This whole section is slated for removal in #19.) */}
      {macros.lines.length > 0 && (
      <section>
        <h2 className="section-title">Per-ingredient breakdown</h2>
        {columns.length === 0 && (
          <p className="muted">
            No macros yet — link each ingredient to a USDA food below to populate this view.
          </p>
        )}
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
              <th aria-label="actions"></th>
            </tr>
          </thead>
          <tbody>
            {macros.lines.map((line, i) => {
              const position = linePosition(recipe, line, i);
              const isOpen = linkingPosition === position;
              return (
                <Fragment key={line.recipe_ingredient_id ?? i}>
                  <tr className={line.resolved ? "" : "is-unresolved"}>
                    <td className="left">
                      {line.ingredient_name}
                      {!line.resolved && <span className="tag tag--warn">not linked</span>}
                    </td>
                    <td>{line.gram_weight != null ? formatAmount(line.gram_weight) : "—"}</td>
                    {columns.map((c) => (
                      <td key={c}>{line.resolved ? formatAmount(line.macros[c]) : "—"}</td>
                    ))}
                    <td className="macro-table__action">
                      {position == null ? null : line.resolved ? (
                        <button className="link-btn" onClick={() => unlink(position)}>
                          Unlink
                        </button>
                      ) : (
                        <button
                          className="link-btn"
                          onClick={() => setLinkingPosition(isOpen ? null : position)}
                        >
                          {isOpen ? "Close" : "Link"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {isOpen && position != null && (
                    <tr className="link-panel-row">
                      <td colSpan={columns.length + 3}>
                        <LinkPanel
                          recipeId={recipe.id}
                          position={position}
                          onLinked={() => {
                            setLinkingPosition(null);
                            reload();
                          }}
                          onCancel={() => setLinkingPosition(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
          {columns.length > 0 && (
            <tfoot>
              <tr>
                <td className="left">Total</td>
                <td></td>
                {columns.map((c) => (
                  <td key={c}>
                    <strong>{formatAmount(macros.totals[c])}</strong>
                  </td>
                ))}
                <td></td>
              </tr>
              {macros.per_serving && (
                <tr className="per-serving-row">
                  <td className="left">Per serving</td>
                  <td></td>
                  {columns.map((c) => (
                    <td key={c}>{formatAmount(macros.per_serving![c])}</td>
                  ))}
                  <td></td>
                </tr>
              )}
            </tfoot>
          )}
        </table>
      </section>
      )}
    </div>
  );
}

// The six per-serving macros the user can record by hand (#18). Keys match the
// recipe schema; units mirror the canonical macro table in api/format.ts.
const MACRO_FIELDS = [
  { key: "calories_per_serving", label: "Calories", unit: "kcal" },
  { key: "protein_per_serving", label: "Protein", unit: "g" },
  { key: "fat_per_serving", label: "Fat", unit: "g" },
  { key: "carbs_per_serving", label: "Carbs", unit: "g" },
  { key: "fiber_per_serving", label: "Fiber", unit: "g" },
  { key: "sodium_per_serving", label: "Sodium", unit: "mg" },
] as const;

type MacroFieldKey = (typeof MACRO_FIELDS)[number]["key"];

function macroValues(recipe: RecipeOut): Record<MacroFieldKey, string> {
  return Object.fromEntries(
    MACRO_FIELDS.map((f) => [f.key, recipe[f.key] != null ? String(recipe[f.key]) : ""]),
  ) as Record<MacroFieldKey, string>;
}

/**
 * Inline editor for the recipe's hand-entered per-serving macros — the primary
 * macro workflow (#18). Saves via the same full-recipe PUT (toUpdateBody carries
 * every other field through unchanged), then asks the parent to reload so the
 * summary cards reflect the new numbers.
 */
function MacroEditor({ recipe, onSaved }: { recipe: RecipeOut; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Record<MacroFieldKey, string>>(() => macroValues(recipe));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const anySet = MACRO_FIELDS.some((f) => recipe[f.key] != null);

  function start() {
    setValues(macroValues(recipe));
    setErr(null);
    setEditing(true);
  }

  async function save() {
    if (saving) return;
    const overrides: Partial<RecipeUpdateBody> = {};
    for (const f of MACRO_FIELDS) {
      const raw = values[f.key].trim();
      if (raw === "") {
        overrides[f.key] = null;
        continue;
      }
      const n = Number(raw);
      if (Number.isNaN(n) || n < 0) {
        setErr(`${f.label} must be a number of 0 or more (or left blank).`);
        return;
      }
      overrides[f.key] = raw;
    }

    setSaving(true);
    setErr(null);
    const { error: apiError } = await api.PUT("/recipes/{recipe_id}", {
      params: { path: { recipe_id: recipe.id } },
      body: toUpdateBody(recipe, overrides),
    });
    setSaving(false);
    if (apiError) {
      setErr("Could not save macros.");
      return;
    }
    setEditing(false);
    onSaved();
  }

  if (!editing) {
    return (
      <section className="macro-entry">
        <div className="macro-entry__head">
          <h2 className="section-title">Macros (per serving)</h2>
          <button className="btn btn--small" onClick={start}>
            {anySet ? "Edit macros" : "Add macros"}
          </button>
        </div>
        {!anySet && (
          <p className="muted">
            No macros recorded yet — add them by hand for quick per-serving tracking.
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="macro-entry">
      <div className="macro-entry__head">
        <h2 className="section-title">Macros (per serving)</h2>
      </div>
      {err && <p className="error">{err}</p>}
      <div className="macro-entry__grid">
        {MACRO_FIELDS.map((f) => (
          <label key={f.key} className="macro-entry__field">
            <span>
              {f.label} <span className="unit">({f.unit})</span>
            </span>
            <input
              type="number"
              min="0"
              step="any"
              inputMode="decimal"
              value={values[f.key]}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              placeholder="—"
            />
          </label>
        ))}
      </div>
      <p className="muted macro-entry__hint">
        Totals roll up as per-serving × {recipe.servings ?? 1} serving
        {(recipe.servings ?? 1) === 1 ? "" : "s"}. Leave a field blank to omit it.
      </p>
      <div className="macro-entry__actions">
        <button className="btn btn--accent" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save macros"}
        </button>
        <button className="btn" onClick={() => setEditing(false)} disabled={saving}>
          Cancel
        </button>
      </div>
    </section>
  );
}

type EditRow = {
  key: string;
  name: string;
  quantity: string;
  unit: string;
  notes: string;
  // Carried through unchanged so editing a line's text doesn't drop its USDA
  // link / provenance; new rows start unlinked (user links them post-save).
  rawText: string | null;
  usdaFdcId: number | null;
  gramWeight: string | null;
};

let rowSeq = 0;
const nextKey = () => `row-${rowSeq++}`;

function toEditRow(line: IngredientLine): EditRow {
  return {
    key: nextKey(),
    name: line.name ?? "",
    quantity: line.quantity != null ? String(line.quantity) : "",
    unit: line.unit ?? "",
    notes: line.notes ?? "",
    rawText: line.raw_text ?? null,
    usdaFdcId: line.usda_fdc_id ?? null,
    gramWeight: line.gram_weight != null ? String(line.gram_weight) : null,
  };
}

function blankRow(): EditRow {
  return {
    key: nextKey(),
    name: "",
    quantity: "",
    unit: "",
    notes: "",
    rawText: null,
    usdaFdcId: null,
    gramWeight: null,
  };
}

/**
 * Edit mode for a recipe: title, description, servings, ingredient rows (add /
 * remove / reorder / retype), and directions. Saves the whole recipe via PUT
 * (toUpdateBody round-trips the full shape), preserving each line's USDA link.
 */
function RecipeEditForm({
  recipe,
  onSaved,
  onCancel,
}: {
  recipe: RecipeOut;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(recipe.title);
  const [description, setDescription] = useState(recipe.description ?? "");
  const [servings, setServings] = useState(
    recipe.servings != null ? String(recipe.servings) : "",
  );
  const [instructions, setInstructions] = useState(recipe.instructions_md ?? "");
  const [rows, setRows] = useState<EditRow[]>(() =>
    [...recipe.ingredients].sort((a, b) => a.position - b.position).map(toEditRow),
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function patchRow(key: string, patch: Partial<EditRow>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function removeRow(key: string) {
    setRows((rs) => rs.filter((r) => r.key !== key));
  }
  function move(key: string, dir: -1 | 1) {
    setRows((rs) => {
      const i = rs.findIndex((r) => r.key === key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= rs.length) return rs;
      const next = [...rs];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  async function save() {
    if (saving) return;
    if (!title.trim()) {
      setErr("Title can't be empty.");
      return;
    }
    if (rows.some((r) => !r.name.trim())) {
      setErr("Every ingredient needs a name — remove any blank rows.");
      return;
    }
    const servingsNum = servings.trim() ? Number(servings) : null;
    if (servingsNum != null && (!Number.isInteger(servingsNum) || servingsNum < 1)) {
      setErr("Servings must be a whole number of at least 1.");
      return;
    }

    setSaving(true);
    setErr(null);
    const body = toUpdateBody(recipe, {
      title: title.trim(),
      description: description.trim() || null,
      servings: servingsNum,
      instructions_md: instructions.trim() || null,
      ingredients: rows.map((r) => ({
        name: r.name.trim(),
        quantity: r.quantity.trim() || null,
        unit: r.unit.trim() || null,
        raw_text: r.rawText,
        notes: r.notes.trim() || null,
        usda_fdc_id: r.usdaFdcId,
        gram_weight: r.gramWeight,
      })),
    });
    const { error: apiError } = await api.PUT("/recipes/{recipe_id}", {
      params: { path: { recipe_id: recipe.id } },
      body,
    });
    setSaving(false);
    if (apiError) {
      setErr("Could not save changes.");
      return;
    }
    onSaved();
  }

  const hasLinks = rows.some((r) => r.usdaFdcId != null);

  return (
    <div className="detail">
      <header className="detail__header">
        <div className="detail__titlebar">
          <h1>Edit recipe</h1>
          <div className="detail__actions">
            <button className="btn btn--accent" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
            <button className="btn" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
          </div>
        </div>
        {err && <p className="error">{err}</p>}
      </header>

      <div className="edit-form">
        <label className="field">
          <span>Title</span>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>

        <label className="field field--narrow">
          <span>Servings</span>
          <input
            type="number"
            min="1"
            step="1"
            value={servings}
            onChange={(e) => setServings(e.target.value)}
          />
        </label>

        <div className="field">
          <span>Ingredients</span>
          <div className="edit-rows">
            <div className="edit-row edit-row--head">
              <span>Qty</span>
              <span>Unit</span>
              <span>Name</span>
              <span>Notes</span>
              <span aria-hidden />
            </div>
            {rows.map((r, i) => (
              <div className="edit-row" key={r.key}>
                <input
                  className="edit-row__qty"
                  type="text"
                  placeholder="1"
                  value={r.quantity}
                  onChange={(e) => patchRow(r.key, { quantity: e.target.value })}
                />
                <input
                  className="edit-row__unit"
                  type="text"
                  placeholder="cup"
                  value={r.unit}
                  onChange={(e) => patchRow(r.key, { unit: e.target.value })}
                />
                <input
                  className="edit-row__name"
                  type="text"
                  placeholder="Ingredient"
                  value={r.name}
                  onChange={(e) => patchRow(r.key, { name: e.target.value })}
                />
                <input
                  className="edit-row__notes"
                  type="text"
                  placeholder="(optional)"
                  value={r.notes}
                  onChange={(e) => patchRow(r.key, { notes: e.target.value })}
                />
                <div className="edit-row__tools">
                  <button
                    type="button"
                    className="link-btn"
                    title="Move up"
                    disabled={i === 0}
                    onClick={() => move(r.key, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="link-btn"
                    title="Move down"
                    disabled={i === rows.length - 1}
                    onClick={() => move(r.key, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="link-btn link-btn--danger"
                    title="Remove ingredient"
                    onClick={() => removeRow(r.key)}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
          <button type="button" className="btn" onClick={() => setRows((rs) => [...rs, blankRow()])}>
            + Add ingredient
          </button>
          {hasLinks && (
            <p className="muted edit-hint">
              USDA links and gram weights are preserved. New rows start unlinked — link
              them from the breakdown after saving.
            </p>
          )}
        </div>

        <label className="field">
          <span>Directions</span>
          <textarea
            rows={10}
            placeholder="One step per line."
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>
      </div>
    </div>
  );
}

/** Map a macro line back to its recipe ingredient's position (the link API key).
 *  Matches on the persisted recipe_ingredient id, falling back to the i-th line. */
function linePosition(
  recipe: RecipeOut,
  line: MacroBreakdown["lines"][number],
  i: number,
): number | null {
  if (line.recipe_ingredient_id != null) {
    const match = recipe.ingredients.find((l) => l.id === line.recipe_ingredient_id);
    if (match) return match.position;
  }
  return recipe.ingredients[i]?.position ?? null;
}

/**
 * Inline panel to link one ingredient line to a USDA food: search FoodData
 * Central, pick a match, enter the gram weight for this line, and confirm.
 */
function LinkPanel({
  recipeId,
  position,
  onLinked,
  onCancel,
}: {
  recipeId: number;
  position: number;
  onLinked: () => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodSummary[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<FoodSummary | null>(null);
  const [grams, setGrams] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function search(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setErr(null);
    const { data, error } = await api.GET("/foods/search", {
      params: { query: { query: q, limit: 10 } },
    });
    setSearching(false);
    setSearched(true);
    if (error) {
      setErr("Search failed. Is the backend running?");
      return;
    }
    setResults(data ?? []);
  }

  async function confirm() {
    if (!selected || !grams.trim() || busy) return;
    setBusy(true);
    setErr(null);
    const { error } = await api.POST(
      "/recipes/{recipe_id}/ingredients/{position}/link",
      {
        params: { path: { recipe_id: recipeId, position } },
        body: { fdc_id: selected.fdc_id, gram_weight: grams.trim() },
      },
    );
    setBusy(false);
    if (error) {
      setErr("Could not link this food. Check the gram weight and try again.");
      return;
    }
    onLinked();
  }

  return (
    <div className="link-panel">
      <form className="link-panel__search" onSubmit={search}>
        <input
          autoFocus
          type="text"
          placeholder="Search USDA foods (e.g. “chicken breast”)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn" type="submit" disabled={searching || !query.trim()}>
          {searching ? "Searching…" : "Search"}
        </button>
        <button className="btn" type="button" onClick={onCancel}>
          Cancel
        </button>
      </form>

      {searched && !searching && results.length === 0 && !err && (
        <p className="muted">No matches found. Try a simpler or different term.</p>
      )}

      {results.length > 0 && (
        <ul className="link-panel__results">
          {results.map((food) => (
            <li key={food.fdc_id}>
              <label>
                <input
                  type="radio"
                  name={`food-${position}`}
                  checked={selected?.fdc_id === food.fdc_id}
                  onChange={() => setSelected(food)}
                />
                <span>{food.description}</span>
                {food.data_type && <span className="tag">{food.data_type}</span>}
              </label>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="link-panel__confirm">
          <label>
            Grams for this ingredient
            <input
              type="number"
              min="0"
              step="any"
              placeholder="e.g. 150"
              value={grams}
              onChange={(e) => setGrams(e.target.value)}
            />
          </label>
          <button
            className="btn btn--accent"
            onClick={confirm}
            disabled={busy || !grams.trim()}
          >
            {busy ? "Linking…" : `Link to ${selected.description}`}
          </button>
        </div>
      )}

      {err && <p className="error">{err}</p>}
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
