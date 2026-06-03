import { useState } from "react";
import "./App.css";
import { HealthBadge } from "./components/HealthBadge";
import { ImportRecipe } from "./components/ImportRecipe";
import { RecipeList } from "./pages/RecipeList";
import { RecipeDetail } from "./pages/RecipeDetail";

function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Bumped whenever the recipe set changes (import, finalize) to reload the list.
  const [listVersion, setListVersion] = useState(0);
  const refreshList = () => setListVersion((v) => v + 1);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1 className="brand__name">Recetario</h1>
          <HealthBadge />
        </div>
        <ImportRecipe
          onImported={(id) => {
            refreshList();
            setSelectedId(id);
          }}
        />
        <RecipeList
          onSelect={setSelectedId}
          selectedId={selectedId}
          reloadKey={listVersion}
        />
      </aside>
      <main className="main">
        {selectedId == null ? (
          <div className="empty">
            <h2>Select a recipe</h2>
            <p className="muted">
              Paste a recipe page or video link above to import one, or pick a recipe
              on the left to see its ingredient-level macro breakdown.
            </p>
          </div>
        ) : (
          <RecipeDetail recipeId={selectedId} onChanged={refreshList} />
        )}
      </main>
    </div>
  );
}

export default App;
