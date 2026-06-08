import { useCallback, useEffect, useState } from "react";
import type { ShoppingList, ShoppingListItem } from "@recetario/core";
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
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

  // Toggle by index: file-backed items have no stable id, and the whole list is
  // rewritten on any change anyway.
  async function toggle(index: number) {
    if (!list) return;
    const items = list.items ?? [];
    const next = { ...list, items: items.map((it, i) => (i === index ? { ...it, checked: !it.checked } : it)) };
    setList(next); // optimistic
    try {
      const { shopping } = await getRepos();
      await shopping.update(next);
      onChanged(); // refresh sidebar counts
    } catch {
      setList(list); // revert
    }
  }

  async function remove() {
    if (!list) return;
    try {
      const { shopping } = await getRepos();
      await shopping.delete(list.id!);
      onDeleted();
    } catch {
      setError("Could not delete this list.");
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!list) return null;

  const items = list.items ?? [];
  const { total, checked } = counts(list);
  const pct = total ? Math.round((checked / total) * 100) : 0;

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
          <button className="btn" onClick={remove} title="Delete this list">
            Delete
          </button>
        </div>
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
          {items.map((item, i) => (
            <li key={i} className={`shop-item ${item.checked ? "is-checked" : ""}`}>
              <label className="shop-item__label">
                <input type="checkbox" checked={item.checked ?? false} onChange={() => toggle(i)} />
                <span>{itemLabel(item)}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
