import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ShoppingItem,
  type ShoppingList,
  type ShoppingListSummary,
} from "../api/client";
import { formatQuantity } from "../api/format";
import { addDays, isoDate, startOfWeek, weekRangeLabel } from "../api/week";

function rangeLabel(start: string, end: string): string {
  const fmt: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const s = new Date(`${start}T00:00:00`).toLocaleDateString(undefined, fmt);
  const e = new Date(`${end}T00:00:00`).toLocaleDateString(undefined, fmt);
  return `${s} – ${e}`;
}

/* ---- Sidebar: generate control + saved lists --------------------------- */

interface SidebarProps {
  onSelect: (id: number) => void;
  selectedId: number | null;
  reloadKey: number;
  onGenerated: (id: number) => void;
}

export function ShoppingSidebar({ onSelect, selectedId, reloadKey, onGenerated }: SidebarProps) {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [lists, setLists] = useState<ShoppingListSummary[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data, error: apiError } = await api.GET("/shopping-lists", { params: {} });
    if (apiError) setError("Could not load shopping lists.");
    else {
      setError(null);
      setLists(data ?? []);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  async function generate() {
    if (generating) return;
    setGenerating(true);
    setError(null);
    const { data, error: apiError } = await api.POST("/shopping-lists", {
      body: { week_start: isoDate(weekStart), week_end: isoDate(addDays(weekStart, 6)) },
    });
    setGenerating(false);
    if (apiError || !data) {
      setError("Could not generate the list.");
      return;
    }
    onGenerated(data.id);
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
          {lists.map((l) => (
            <li key={l.id}>
              <button
                className={`recipe-list__item ${l.id === selectedId ? "is-active" : ""}`}
                onClick={() => onSelect(l.id)}
              >
                <span className="recipe-list__title">{l.name}</span>
                <span className="recipe-list__meta">
                  <span className="muted">{rangeLabel(l.week_start, l.week_end)}</span>
                  <span className="pill">
                    {l.checked_count}/{l.item_count}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---- Main: the selected list's items with check-off -------------------- */

function itemLabel(item: ShoppingItem): string {
  const qty = formatQuantity(item.total_quantity);
  const amount = [qty, item.unit?.trim()].filter(Boolean).join(" ");
  return amount ? `${item.ingredient_name} — ${amount}` : item.ingredient_name;
}

interface DetailProps {
  listId: number;
  /** After a check-off, so the sidebar counts refresh (selection stays). */
  onChanged: () => void;
  /** After deletion, so the parent clears the selection. */
  onDeleted: () => void;
}

export function ShoppingListDetail({ listId, onChanged, onDeleted }: DetailProps) {
  const [list, setList] = useState<ShoppingList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      const { data, error: apiError } = await api.GET("/shopping-lists/{list_id}", {
        params: { path: { list_id: listId } },
      });
      if (!active) return;
      if (apiError || !data) setError("Could not load this shopping list.");
      else {
        setError(null);
        setList(data);
      }
      setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [listId]);

  async function toggle(item: ShoppingItem) {
    if (!list) return;
    const next = !item.checked;
    // Optimistic update; revert on failure.
    setList({
      ...list,
      items: list.items.map((i) => (i.id === item.id ? { ...i, checked: next } : i)),
    });
    const { error: apiError } = await api.PATCH("/shopping-lists/{list_id}/items/{item_id}", {
      params: { path: { list_id: list.id, item_id: item.id } },
      body: { checked: next },
    });
    if (apiError) {
      setList({
        ...list,
        items: list.items.map((i) => (i.id === item.id ? { ...i, checked: item.checked } : i)),
      });
    } else {
      onChanged(); // refresh sidebar counts
    }
  }

  async function remove() {
    if (!list) return;
    const { error: apiError } = await api.DELETE("/shopping-lists/{list_id}", {
      params: { path: { list_id: list.id } },
    });
    if (!apiError) onDeleted();
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!list) return null;

  const checked = list.items.filter((i) => i.checked).length;
  const total = list.items.length;
  const pct = total ? Math.round((checked / total) * 100) : 0;

  return (
    <div className="shop-detail">
      <header className="shop-detail__header">
        <div>
          <h1>{list.name}</h1>
          <p className="detail__meta muted">
            {rangeLabel(list.week_start, list.week_end)} · {checked}/{total} checked
          </p>
        </div>
        <button className="btn" onClick={remove} title="Delete this list">
          Delete
        </button>
      </header>

      {total > 0 && (
        <div className="progress">
          <div className="progress__bar" style={{ width: `${pct}%` }} />
        </div>
      )}

      {total === 0 ? (
        <p className="muted">
          This week has no scheduled meals, so the list is empty. Plan some meals in the
          Calendar, then regenerate.
        </p>
      ) : (
        <ul className="shop-items">
          {list.items.map((item) => (
            <li key={item.id} className={`shop-item ${item.checked ? "is-checked" : ""}`}>
              <label className="shop-item__label">
                <input
                  type="checkbox"
                  checked={item.checked}
                  onChange={() => toggle(item)}
                />
                <span>{itemLabel(item)}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
