import { useState } from "react";
import { api } from "../api/client";
import type { paths } from "../api/schema";

type RecipeCreateBody =
  paths["/recipes"]["post"]["requestBody"]["content"]["application/json"];

interface Props {
  /** Called with the new recipe's id after it's created, so the app can open it. */
  onCreated: (recipeId: number) => void;
  /** Called when the user backs out without creating anything. */
  onCancel: () => void;
}

type IngredientRow = {
  key: string;
  name: string;
  quantity: string;
  unit: string;
  notes: string;
};

let rowSeq = 0;
const nextKey = () => `new-row-${rowSeq++}`;

function blankRow(): IngredientRow {
  return { key: nextKey(), name: "", quantity: "", unit: "", notes: "" };
}

/**
 * Manual recipe creation. The app could only import recipes from a URL before;
 * this lets the user type one in from scratch (a cookbook, a family recipe, etc.).
 *
 * It mirrors the in-place edit form on RecipeDetail, but POSTs a brand-new recipe
 * as source_type "manual" / status "finalized" (no draft-review step is needed
 * for something the user typed themselves). Macros come later by linking
 * ingredients to USDA foods on the detail view.
 */
export function NewRecipe({ onCreated, onCancel }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [servings, setServings] = useState("");
  const [tags, setTags] = useState("");
  const [instructions, setInstructions] = useState("");
  // Start with a couple of empty rows so the table reads as fillable.
  const [rows, setRows] = useState<IngredientRow[]>(() => [blankRow(), blankRow()]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function patchRow(key: string, patch: Partial<IngredientRow>) {
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
      setErr("Give your recipe a title.");
      return;
    }
    const servingsNum = servings.trim() ? Number(servings) : null;
    if (servingsNum != null && (!Number.isInteger(servingsNum) || servingsNum < 1)) {
      setErr("Servings must be a whole number of at least 1.");
      return;
    }
    // Blank rows are scaffolding, not real ingredients — drop them silently.
    const filledRows = rows.filter((r) => r.name.trim());

    setSaving(true);
    setErr(null);
    const body: RecipeCreateBody = {
      title: title.trim(),
      description: description.trim() || null,
      source_type: "manual",
      status: "finalized",
      servings: servingsNum,
      instructions_md: instructions.trim() || null,
      ingredients: filledRows.map((r) => ({
        name: r.name.trim(),
        quantity: r.quantity.trim() || null,
        unit: r.unit.trim() || null,
        notes: r.notes.trim() || null,
      })),
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length),
    };
    const { data, error: apiError } = await api.POST("/recipes", { body });
    setSaving(false);
    if (apiError || !data) {
      setErr("Could not create this recipe. Is the backend running?");
      return;
    }
    onCreated(data.id);
  }

  return (
    <div className="detail">
      <header className="detail__header">
        <div className="detail__titlebar">
          <h1>New recipe</h1>
          <div className="detail__actions">
            <button className="btn btn--accent" onClick={save} disabled={saving}>
              {saving ? "Creating…" : "Create recipe"}
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
          <input
            type="text"
            autoFocus
            placeholder="e.g. Grandma's lasagna"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>

        <label className="field">
          <span>Description</span>
          <textarea
            rows={2}
            placeholder="(optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>

        <div className="new-recipe__split">
          <label className="field field--narrow">
            <span>Servings</span>
            <input
              type="number"
              min="1"
              step="1"
              placeholder="4"
              value={servings}
              onChange={(e) => setServings(e.target.value)}
            />
          </label>

          <label className="field">
            <span>Tags</span>
            <input
              type="text"
              placeholder="dinner, italian (comma-separated)"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          </label>
        </div>

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
          <button
            type="button"
            className="btn"
            onClick={() => setRows((rs) => [...rs, blankRow()])}
          >
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
