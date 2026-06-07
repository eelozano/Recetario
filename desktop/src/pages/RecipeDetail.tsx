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
 * Recipe detail: ingredients, directions, and hand-entered per-serving macros
 * (with the resulting totals/per-serving cards). For imported drafts it also
 * offers the review → finalize step.
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

  useEffect(() => {
    let active = true;
    setConfirmingDelete(false);
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

  // Reload recipe + macros in place after an edit, and refresh the parent list.
  function reload() {
    setVersion((v) => v + 1);
    onChanged?.();
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
        </div>
        {recipe.description && <p className="detail__desc">{recipe.description}</p>}
      </header>

      {isDraft && (
        <div className="draft-banner">
          <div>
            <strong>Imported draft</strong>
            <p className="muted">
              Review the ingredients and directions below, then finalize to add it
              to your collection.
            </p>
          </div>
          <button className="btn btn--accent" onClick={finalize} disabled={finalizing}>
            {finalizing ? "Finalizing…" : "Finalize recipe"}
          </button>
        </div>
      )}

      {/* Cooking content first; the entered macros and resulting totals follow. */}
      <IngredientList ingredients={recipe.ingredients} />

      <Directions instructionsMd={recipe.instructions_md} />

      <MacroEditor recipe={recipe} onSaved={reload} />

      <SummaryCards macros={macros} columns={columns} />
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
  // Carried through unchanged so editing a line's text never drops its parsed
  // provenance or any legacy USDA link/gram weight still stored on the row.
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
 * (toUpdateBody round-trips the full shape, including any stored macro fields).
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
