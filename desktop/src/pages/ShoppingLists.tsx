import { useCallback, useEffect, useState } from "react";
import {
  CATEGORY_LABELS,
  SHOPPING_CATEGORIES,
  categorizeIngredient,
  normalizeIngredientName,
  type CustomCategory,
  type ShoppingList,
  type ShoppingListItem,
} from "@recetario/core";
import { getRepos } from "../data/repos";
import { generateShoppingList } from "../data/queries";
import { formatQuantity } from "../api/format";
import { addDays, isoDate, startOfWeek, weekRangeLabel } from "../api/week";

function rangeLabel(start: string, end: string): string {
  const fmt: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const s = new Date(`${start}T00:00:00`).toLocaleDateString(undefined, fmt);
  const e = new Date(`${end}T00:00:00`).toLocaleDateString(undefined, fmt);
  return `${s} – ${e}`;
}

function counts(list: ShoppingList): { total: number; checked: number } {
  const items = list.items ?? [];
  return { total: items.length, checked: items.filter((i) => i.checked).length };
}

/**
 * Sentinel for the row picker's "Auto (reset)" choice — clears the saved
 * preference instead of setting a category. Leading-underscore ids are
 * rejected by CustomCategoriesStore, so this can't collide.
 */
const RESET_OPTION = "__reset";

/* ---- Sidebar: generate control + saved lists --------------------------- */

interface SidebarProps {
  onSelect: (id: string) => void;
  selectedId: string | null;
  reloadKey: number;
  onGenerated: (id: string) => void;
}

export function ShoppingSidebar({ onSelect, selectedId, reloadKey, onGenerated }: SidebarProps) {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [lists, setLists] = useState<ShoppingList[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { shopping } = await getRepos();
      const data = await shopping.list();
      // Newest week first, then name.
      data.sort(
        (a, b) => b.weekStart.localeCompare(a.weekStart) || a.name.localeCompare(b.name),
      );
      setError(null);
      setLists(data);
    } catch {
      setError("Could not load shopping lists.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  async function generate() {
    if (generating) return;
    setGenerating(true);
    setError(null);
    try {
      const list = await generateShoppingList(
        isoDate(weekStart),
        isoDate(addDays(weekStart, 6)),
      );
      onGenerated(list.id!);
    } catch {
      setError("Could not generate the list.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="shop-side">
      <div className="shop-gen">
        <div className="shop-gen__week">
          <button className="btn shop-gen__nav" onClick={() => setWeekStart(addDays(weekStart, -7))}>
            ‹
          </button>
          <span className="shop-gen__label">{weekRangeLabel(weekStart)}</span>
          <button className="btn shop-gen__nav" onClick={() => setWeekStart(addDays(weekStart, 7))}>
            ›
          </button>
        </div>
        <button className="btn btn--accent" onClick={generate} disabled={generating}>
          {generating ? "Generating…" : "Generate list from this week"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {lists.length === 0 ? (
        <p className="muted">No shopping lists yet. Generate one from a planned week.</p>
      ) : (
        <ul className="recipe-list">
          {lists.map((l) => {
            const { total, checked } = counts(l);
            return (
              <li key={l.id}>
                <button
                  className={`recipe-list__item ${l.id === selectedId ? "is-active" : ""}`}
                  onClick={() => onSelect(l.id!)}
                >
                  <span className="recipe-list__title">{l.name}</span>
                  <span className="recipe-list__meta">
                    <span className="muted">{rangeLabel(l.weekStart, l.weekEnd)}</span>
                    <span className="pill">
                      {checked}/{total}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ---- Main: the selected list's items with check-off -------------------- */

function itemLabel(item: ShoppingListItem): string {
  const qty = item.totalQuantity != null ? formatQuantity(item.totalQuantity.toString()) : null;
  const amount = [qty, item.unit?.trim()].filter(Boolean).join(" ");
  return amount ? `${item.ingredientName} — ${amount}` : item.ingredientName;
}

interface DetailProps {
  listId: string;
  /** After a check-off, so the sidebar counts refresh (selection stays). */
  onChanged: () => void;
  /** After deletion, so the parent clears the selection. */
  onDeleted: () => void;
}

export function ShoppingListDetail({ listId, onChanged, onDeleted }: DetailProps) {
  const [list, setList] = useState<ShoppingList | null>(null);
  const [customs, setCustoms] = useState<CustomCategory[]>([]);
  const [newItem, setNewItem] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Two-step delete confirmation (window.confirm is unreliable in the webview).
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // User-defined categories (managed in Settings) shape the groups and the
  // row picker. Reloaded per list selection so Settings edits show up.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { customCategories } = await getRepos();
        const data = await customCategories.load();
        if (active) setCustoms(data);
      } catch {
        // Non-fatal: groups fall back to the presets.
      }
    })();
    return () => {
      active = false;
    };
  }, [listId]);

  useEffect(() => {
    let active = true;
    setConfirmingDelete(false);
    (async () => {
      setLoading(true);
      try {
        const { shopping } = await getRepos();
        const data = await shopping.getById(listId);
        if (!active) return;
        setList(data);
        if (!data) setError("Could not load this shopping list.");
        else setError(null);
      } catch {
        if (active) setError("Could not load this shopping list.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [listId]);

  // All mutations go by source index: file-backed items have no stable id, and
  // the whole list is rewritten on any change anyway.
  async function persist(next: ShoppingList): Promise<boolean> {
    const previous = list;
    setList(next); // optimistic
    try {
      const { shopping } = await getRepos();
      await shopping.update(next);
      onChanged(); // refresh sidebar counts
      return true;
    } catch {
      setList(previous); // revert
      return false;
    }
  }

  async function toggle(index: number) {
    if (!list) return;
    const items = list.items ?? [];
    await persist({
      ...list,
      items: items.map((it, i) => (i === index ? { ...it, checked: !it.checked } : it)),
    });
  }

  async function removeItem(index: number) {
    if (!list) return;
    const items = list.items ?? [];
    await persist({ ...list, items: items.filter((_, i) => i !== index) });
  }

  // Move the item to another aisle and remember the choice as a preference, so
  // every future generated list puts this ingredient there too.
  async function recategorize(index: number, category: string) {
    if (!list) return;
    const items = list.items ?? [];
    const item = items[index];
    if (!item) return;
    const ok = await persist({
      ...list,
      items: items.map((it, i) => (i === index ? { ...it, category } : it)),
    });
    if (!ok) return;
    try {
      const { categoryOverrides } = await getRepos();
      await categoryOverrides.set(item.ingredientName, category);
    } catch {
      // The list itself saved; the preference just won't carry forward.
    }
  }

  // Drop the saved preference and fall back to the static map. An import-time
  // LLM category isn't recoverable from the list item, so it reappears on the
  // next regeneration rather than instantly.
  async function resetCategory(index: number) {
    if (!list) return;
    const items = list.items ?? [];
    const item = items[index];
    if (!item) return;
    const fallback = categorizeIngredient(item.ingredientName);
    const ok = await persist({
      ...list,
      items: items.map((it, i) => (i === index ? { ...it, category: fallback } : it)),
    });
    if (!ok) return;
    try {
      const { categoryOverrides } = await getRepos();
      await categoryOverrides.remove(item.ingredientName);
    } catch {
      // The list itself saved; the stale preference resurfaces next generation.
    }
  }

  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    if (!list) return;
    const name = newItem.trim();
    if (!name) return;
    const items = list.items ?? [];
    // Manual items get a best-effort aisle: the user's saved preference first,
    // then the static map ("milk" → Dairy).
    let category: string | null = null;
    try {
      const { categoryOverrides } = await getRepos();
      category =
        (await categoryOverrides.load()).get(normalizeIngredientName(name)) ?? null;
    } catch {
      // No overrides available — fall through to the static map.
    }
    category ??= categorizeIngredient(name);
    const ok = await persist({
      ...list,
      items: [...items, { ingredientName: name, checked: false, category }],
    });
    if (ok) setNewItem(""); // keep the text on failure so the user can retry
  }

  async function remove() {
    if (!list || deleting) return;
    setDeleting(true);
    try {
      const { shopping } = await getRepos();
      await shopping.delete(list.id!);
      onDeleted();
    } catch {
      setError("Could not delete this list.");
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!list) return null;

  const items = list.items ?? [];
  const { total, checked } = counts(list);
  const pct = total ? Math.round((checked / total) * 100) : 0;

  // Display order only — stored order stays put so unchecking restores an
  // item's place, and rows carry their source index for mutations. Items are
  // bucketed by aisle category (unrecognized → "other"), and within each group
  // checked items sink to the bottom (stable sort keeps stored order). Buckets:
  // presets in store-walk order, then the user's custom categories, then Other.
  const buckets: { id: string; label: string }[] = [
    ...SHOPPING_CATEGORIES.filter((c) => c !== "other").map((c) => ({
      id: c as string,
      label: CATEGORY_LABELS[c],
    })),
    ...customs.map((c) => ({ id: c.id, label: c.label })),
    { id: "other", label: CATEGORY_LABELS.other },
  ];
  const known = new Set(buckets.map((b) => b.id));
  const rows = items.map((item, index) => ({ item, index }));
  const groups = buckets
    .map((bucket) => ({
      ...bucket,
      rows: rows
        .filter(
          (r) =>
            (r.item.category && known.has(r.item.category)
              ? r.item.category
              : "other") === bucket.id,
        )
        .sort(
          (a, b) => Number(a.item.checked ?? false) - Number(b.item.checked ?? false),
        ),
    }))
    .filter((g) => g.rows.length > 0);
  // An entirely uncategorized list (older files, all-manual) renders flat —
  // a lone "Other" header would be noise.
  const showHeaders = !(groups.length === 1 && groups[0].id === "other");

  return (
    <div className="shop-detail">
      <header className="shop-detail__header">
        <div>
          <h1>{list.name}</h1>
          <p className="detail__meta muted">
            {rangeLabel(list.weekStart, list.weekEnd)} · {checked}/{total} checked
          </p>
        </div>
        <div className="shop-detail__actions">
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
              title="Delete this list"
            >
              Delete
            </button>
          )}
        </div>
      </header>

      {total > 0 && (
        <div className="progress">
          <div className="progress__bar" style={{ width: `${pct}%` }} />
        </div>
      )}

      {total === 0 ? (
        <p className="muted">
          This list is empty. Plan some meals in the Calendar and regenerate, or add
          items below.
        </p>
      ) : (
        groups.map((group) => (
          <section key={group.id} className="shop-group">
            {showHeaders && <h3 className="shop-group__title">{group.label}</h3>}
            <ul className="shop-items">
              {group.rows.map(({ item, index }) => (
                <li key={index} className={`shop-item ${item.checked ? "is-checked" : ""}`}>
                  <label className="shop-item__label">
                    <input
                      type="checkbox"
                      checked={item.checked ?? false}
                      onChange={() => toggle(index)}
                    />
                    <span>{itemLabel(item)}</span>
                  </label>
                  <select
                    className="shop-item__cat"
                    title="Category — picking one is remembered for future lists"
                    value={group.id}
                    onChange={(e) =>
                      e.target.value === RESET_OPTION
                        ? resetCategory(index)
                        : recategorize(index, e.target.value)
                    }
                  >
                    {buckets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.label}
                      </option>
                    ))}
                    <option value={RESET_OPTION}>Auto (reset)</option>
                  </select>
                  <button
                    className="shop-item__remove"
                    title="Remove item"
                    onClick={() => removeItem(index)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      <form className="shop-add" onSubmit={addItem}>
        <input
          type="text"
          placeholder="Add an item — e.g. paper towels"
          value={newItem}
          onChange={(e) => setNewItem(e.target.value)}
        />
        <button type="submit" className="btn" disabled={!newItem.trim()}>
          Add
        </button>
      </form>
    </div>
  );
}
