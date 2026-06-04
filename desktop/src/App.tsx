import { useState } from "react";
import "./App.css";
import { HealthBadge } from "./components/HealthBadge";
import { ImportRecipe } from "./components/ImportRecipe";
import { RecipeList } from "./pages/RecipeList";
import { RecipeDetail } from "./pages/RecipeDetail";
import { WeekCalendar } from "./pages/WeekCalendar";

type View = "recipes" | "calendar";

function App() {
  const [view, setView] = useState<View>("recipes");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Bumped whenever the recipe set changes (import, finalize) to reload the list
  // and the calendar's recipe picker.
  const [listVersion, setListVersion] = useState(0);
  const refreshList = () => setListVersion((v) => v + 1);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1 className="brand__name">Recetario</h1>
          <HealthBadge />
        </div>

        <nav className="nav">
          <button
            className={`nav__item ${view === "recipes" ? "is-active" : ""}`}
            onClick={() => setView("recipes")}
          >
            Recipes
          </button>
          <button
            className={`nav__item ${view === "calendar" ? "is-active" : ""}`}
            onClick={() => setView("calendar")}
          >
            Calendar
          </button>
        </nav>

        {view === "recipes" && (
          <>
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
          </>
        )}
        {view === "calendar" && (
          <p className="sidebar__hint muted">
            Click a meal slot to schedule a recipe. Day and week totals reuse each
            recipe's macros.
          </p>
        )}
      </aside>
      <main className="main">
        {view === "calendar" ? (
          <WeekCalendar reloadKey={listVersion} />
        ) : selectedId == null ? (
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
