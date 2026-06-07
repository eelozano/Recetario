interface Props {
  /** Called with the new recipe's id once an import finishes (unused while disabled). */
  onImported: (recipeId: string) => void;
}

/**
 * Import-from-URL box — temporarily disabled (Architecture v2, step 3).
 *
 * Recipe ingestion (recipe-scrapers / yt-dlp / Claude) lives in the Python
 * backend, which writes to its own SQLite. Now that recipes are read from flat
 * files, an import would land in a store the UI no longer reads, so the control
 * is stubbed until the ingestion helper is re-wired to write through the core
 * (the next step). Manual recipe entry (+ New recipe) is unaffected.
 */
export function ImportRecipe(_props: Props) {
  return (
    <div className="import import--disabled">
      <span className="import__label">Import from URL</span>
      <p className="muted import__hint">
        Paused while the app moves to local files. Recipe import (web &amp; video)
        returns in the next step. For now, add recipes with{" "}
        <strong>+ New recipe</strong>.
      </p>
    </div>
  );
}
