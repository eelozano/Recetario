/**
 * Settings — data folder picker (Architecture v2, step 5).
 *
 * Recetario keeps every recipe, meal-calendar, and shopping-list file under one
 * data directory. By default that's `~/Documents/Recetario/data`; here the user
 * can point it at any folder — e.g. a Dropbox/iCloud folder to sync across
 * machines. The choice is saved in `~/.recetario/config.json` by the Rust side,
 * which also unlocks a custom folder in the fs scope. Changing the folder reloads
 * the window so the repositories rebuild against the new path; it re-points only
 * (no files are moved), so an existing store in the chosen folder is picked up
 * as-is and an empty one simply starts empty.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { CATEGORY_LABELS, asShoppingCategory, type CustomCategory } from "@recetario/core";

import { getRepos } from "../data/repos";

export function Settings() {
  const [dataDir, setDataDir] = useState<string | null>(null);
  const [defaultDir, setDefaultDir] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [current, fallback] = await Promise.all([
          invoke<string>("get_data_dir"),
          invoke<string>("get_default_data_dir"),
        ]);
        if (!active) return;
        setDataDir(current);
        setDefaultDir(fallback);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const isCustom = dataDir != null && defaultDir != null && dataDir !== defaultDir;

  async function changeFolder() {
    if (busy) return;
    setError(null);
    try {
      const picked = await open({
        directory: true,
        multiple: false,
        title: "Choose a folder for your Recetario data",
        defaultPath: dataDir ?? undefined,
      });
      if (typeof picked !== "string") return; // cancelled
      setBusy(true);
      await invoke("set_data_dir", { path: picked });
      // Reload so the data layer (data/repos.ts) rebuilds against the new dir.
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  async function resetFolder() {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await invoke("reset_data_dir");
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="settings">
      <h2>Settings</h2>

      <section className="settings__section">
        <h3 className="settings__heading">Data folder</h3>
        <p className="muted settings__intro">
          Your recipes, meal calendar, and shopping lists are stored as files in this
          folder. Point it at a synced folder (Dropbox, iCloud Drive…) to share your
          data across machines. Changing it switches Recetario to that folder — your
          existing files aren't moved.
        </p>

        <div className="settings__path-row">
          <code className="settings__path">{dataDir ?? "Loading…"}</code>
          {isCustom && <span className="pill">custom</span>}
        </div>

        <div className="settings__actions">
          <button className="btn btn--accent" onClick={changeFolder} disabled={busy || dataDir == null}>
            {busy ? "Working…" : "Change folder…"}
          </button>
          {isCustom && (
            <button className="btn" onClick={resetFolder} disabled={busy}>
              Reset to default
            </button>
          )}
        </div>

        {error && <p className="error settings__error">{error}</p>}
      </section>

      <ShoppingCategorySettings />

      <p className="muted settings__footnote">
        Recipe import uses an Anthropic API key read from{" "}
        <code>~/.recetario/.env</code>. Editing it from here comes in a later update.
      </p>
    </div>
  );
}

/**
 * Shopping-category customization (#69): user-defined categories (extra groups
 * beyond the preset six) and the saved aisle preferences (per-ingredient
 * overrides written when a list item is recategorized).
 */
function ShoppingCategorySettings() {
  const [customs, setCustoms] = useState<CustomCategory[]>([]);
  const [overrides, setOverrides] = useState<Map<string, string>>(new Map());
  const [newLabel, setNewLabel] = useState("");
  const [prefFilter, setPrefFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const { customCategories, categoryOverrides } = await getRepos();
      setCustoms(await customCategories.load());
      setOverrides(await categoryOverrides.load());
    } catch {
      setError("Could not load shopping category settings.");
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Display label for a category id: preset label, custom label, or — for an
  // override pointing at a deleted custom category — the raw id.
  function labelOf(id: string): string {
    const preset = asShoppingCategory(id);
    if (preset !== null) return CATEGORY_LABELS[preset];
    return customs.find((c) => c.id === id)?.label ?? id;
  }

  // Alphabetical, narrowed by the filter box (matches the ingredient name or
  // the category it maps to).
  const visiblePrefs = [...overrides.entries()].sort().filter(([name, category]) => {
    const q = prefFilter.trim().toLowerCase();
    if (!q) return true;
    return name.includes(q) || labelOf(category).toLowerCase().includes(q);
  });

  async function addCategory(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { customCategories } = await getRepos();
      await customCategories.add(newLabel);
      setNewLabel("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the category.");
    }
  }

  async function removeCategory(id: string) {
    setError(null);
    try {
      const { customCategories } = await getRepos();
      await customCategories.remove(id);
      await reload();
    } catch {
      setError("Could not remove the category.");
    }
  }

  async function removeOverride(name: string) {
    setError(null);
    try {
      const { categoryOverrides } = await getRepos();
      await categoryOverrides.remove(name);
      await reload();
    } catch {
      setError("Could not remove the preference.");
    }
  }

  async function clearOverrides() {
    setError(null);
    try {
      const { categoryOverrides } = await getRepos();
      await categoryOverrides.clear();
      await reload();
    } catch {
      setError("Could not clear the preferences.");
    }
  }

  return (
    <section className="settings__section">
      <h3 className="settings__heading">Shopping categories</h3>
      <p className="muted settings__intro">
        Add your own sections to the shopping list (say, splitting Produce into Fruit
        and Veggies). Imports keep using the built-in six; move items into a custom
        section from the list itself, and the choice sticks. Deleting a section sends
        its items back to Other.
      </p>

      <form className="settings__add-row" onSubmit={addCategory}>
        <input
          type="text"
          placeholder="New category — e.g. Fruit"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
        />
        <button type="submit" className="btn" disabled={!newLabel.trim()}>
          Add
        </button>
      </form>

      {customs.length > 0 && (
        <ul className="settings__chips">
          {customs.map((c) => (
            <li key={c.id} className="settings__chip">
              {c.label}
              <button
                className="settings__chip-remove"
                title={`Remove "${c.label}"`}
                onClick={() => removeCategory(c.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <h4 className="settings__subheading">
        Aisle preferences{overrides.size > 0 && ` (${overrides.size})`}
      </h4>
      {overrides.size === 0 ? (
        <p className="muted">
          None yet. Pick a category on a shopping list item and it's remembered here.
        </p>
      ) : (
        <>
          {overrides.size > 8 && (
            <input
              className="settings__filter"
              type="search"
              placeholder="Filter preferences…"
              value={prefFilter}
              onChange={(e) => setPrefFilter(e.target.value)}
            />
          )}
          {visiblePrefs.length === 0 ? (
            <p className="muted">No preferences match “{prefFilter.trim()}”.</p>
          ) : (
            <ul className="settings__prefs">
              {visiblePrefs.map(([name, category]) => (
                <li key={name} className="settings__pref">
                  <span className="settings__pref-name">{name}</span>
                  <span className="muted">→ {labelOf(category)}</span>
                  <button
                    className="settings__chip-remove"
                    title={`Forget the preference for "${name}"`}
                    onClick={() => removeOverride(name)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button className="btn" onClick={clearOverrides}>
            Clear all preferences
          </button>
        </>
      )}

      {error && <p className="error settings__error">{error}</p>}
    </section>
  );
}
