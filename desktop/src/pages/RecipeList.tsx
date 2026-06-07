import { useEffect, useState } from "react";
import { api, type RecipeSummary } from "../api/client";

interface Props {
  onSelect: (recipeId: number) => void;
  selectedId: number | null;
  /** Bump to force a reload (e.g. after an import or finalize). */
  reloadKey?: number;
}

/** Left-hand list of recipes. Clicking one opens its macro breakdown. */
export function RecipeList({ onSelect, selectedId, reloadKey }: Props) {
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      const { data, error } = await api.GET("/recipes", { params: { query: {} } });
      if (!active) return;
      if (error) setError("Could not load recipes");
      else {
        setError(null);
        setRecipes(data ?? []);
      }
      setLoading(false);
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
        No recipes yet. Click <strong>+ New recipe</strong> to add one by hand, or
        paste a recipe link above to import one.
      </p>
    );

  return (
    <ul className="recipe-list">
      {recipes.map((r) => (
        <li key={r.id}>
          <button
            className={`recipe-list__item ${r.id === selectedId ? "is-active" : ""}`}
            onClick={() => onSelect(r.id)}
          >
            <span className="recipe-list__title">{r.title}</span>
            <span className="recipe-list__meta">
              <span className={`pill pill--${r.status}`}>{r.status}</span>
              {r.servings != null && <span className="muted">{r.servings} servings</span>}
            </span>
            {r.tags.length > 0 && (
              <span className="recipe-list__tags">
                {r.tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
