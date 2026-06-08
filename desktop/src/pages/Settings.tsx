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
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

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

      <p className="muted settings__footnote">
        Recipe import uses an Anthropic API key read from{" "}
        <code>~/.recetario/.env</code>. Editing it from here comes in a later update.
      </p>
    </div>
  );
}
