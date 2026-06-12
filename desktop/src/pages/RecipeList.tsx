import { useEffect, useState } from "react";
import type { Recipe } from "@recetario/core";
import { getRepos } from "../data/repos";
import { filterRecipes } from "../api/recipe-search";

interface Props {
  onSelect: (recipeId: string) => void;
  selectedId: string | null;
  /** Bump to force a reload (e.g. after a create or finalize). */
  reloadKey?: number;
}

/** Left-hand list of recipes. Clicking one opens its macro breakdown. */
export function RecipeList({ onSelect, selectedId, reloadKey }: Props) {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const { recipes } = await getRepos();
        const data = await recipes.list();
        if (!active) return;
        setError(null);
        // Stable display order: title, case-insensitive.
        data.sort((a, b) => a.title.toLowerCase().localeCompare(b.title.toLowerCase()));
        setRecipes(data);
      } catch {
        if (active) setError("Could not load recipes");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [reloadKey]);

  if (loading) return <p className="muted">Loading recipes…</p>;
  if (error) return <p className="error">{error}</p>;
  if (recipes.length === 0)
    return (
      <p className="muted">
        No recipes yet. Click <strong>+ New recipe</strong> to add one by hand.
      </p>
    );

  const visible = filterRecipes(recipes, query);

  return (
    <>
      <input
        className="sidebar-search"
        type="search"
        placeholder="Search recipes…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setQuery("");
        }}
      />
      {visible.length === 0 ? (
        <p className="muted">No recipes match “{query.trim()}”.</p>
      ) : (
        <ul className="recipe-list">
          {visible.map((r) => (
            <li key={r.id}>
              <button
                className={`recipe-list__item ${r.id === selectedId ? "is-active" : ""}`}
                onClick={() => onSelect(r.id!)}
              >
                <span className="recipe-list__title">{r.title}</span>
                <span className="recipe-list__meta">
                  <span className={`pill pill--${r.status}`}>{r.status}</span>
                  {r.servings != null && (
                    <span className="muted">{r.servings} servings</span>
                  )}
                </span>
                {(r.tags?.length ?? 0) > 0 && (
                  <span className="recipe-list__tags">
                    {r.tags!.map((t) => (
                      <span key={t.name} className="tag">
                        {t.name}
                      </span>
                    ))}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
