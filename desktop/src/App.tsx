import { useState } from "react";
import "./App.css";
import { HealthBadge } from "./components/HealthBadge";
import { RecipeList } from "./pages/RecipeList";
import { RecipeDetail } from "./pages/RecipeDetail";

function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1 className="brand__name">Recetario</h1>
          <HealthBadge />
        </div>
        <RecipeList onSelect={setSelectedId} selectedId={selectedId} />
      </aside>
      <main className="main">
        {selectedId == null ? (
          <div className="empty">
            <h2>Select a recipe</h2>
            <p className="muted">
              Pick a recipe on the left to see its ingredient-level macro breakdown.
            </p>
          </div>
        ) : (
          <RecipeDetail recipeId={selectedId} />
        )}
      </main>
    </div>
  );
}

export default App;
