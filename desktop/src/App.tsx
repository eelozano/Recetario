import { useState } from "react";
import "./App.css";
import { ImportRecipe } from "./components/ImportRecipe";
import { RecipeList } from "./pages/RecipeList";
import { RecipeDetail } from "./pages/RecipeDetail";
import { WeekCalendar } from "./pages/WeekCalendar";
import { ShoppingSidebar, ShoppingListDetail } from "./pages/ShoppingLists";
import { Settings } from "./pages/Settings";
import { NewRecipe } from "./pages/NewRecipe";

type View = "recipes" | "calendar" | "shopping" | "settings";

function App() {
  const [view, setView] = useState<View>("recipes");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // When true (in the recipes view), the main panel shows the manual-create form.
  const [creating, setCreating] = useState(false);
  const [selectedShoppingId, setSelectedShoppingId] = useState<string | null>(null);
  // Bumped whenever the recipe set changes (import, finalize) to reload the list
  // and the calendar's recipe picker.
  const [listVersion, setListVersion] = useState(0);
  const refreshList = () => setListVersion((v) => v + 1);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1 className="brand__name">Recetario</h1>
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
          <button
            className={`nav__item ${view === "shopping" ? "is-active" : ""}`}
            onClick={() => setView("shopping")}
          >
            Shopping
          </button>
          <button
            className={`nav__item ${view === "settings" ? "is-active" : ""}`}
            onClick={() => setView("settings")}
          >
            Settings
          </button>
        </nav>

        {view === "recipes" && (
          <>
            <button
              className="btn btn--accent sidebar__new-recipe"
              onClick={() => {
                setCreating(true);
                setSelectedId(null);
              }}
            >
              + New recipe
            </button>
            <ImportRecipe
              onImported={(id) => {
                refreshList();
                setCreating(false);
                setSelectedId(id);
              }}
            />
            <RecipeList
              onSelect={(id) => {
                setCreating(false);
                setSelectedId(id);
              }}
              selectedId={creating ? null : selectedId}
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
        {view === "shopping" && (
          <ShoppingSidebar
            onSelect={setSelectedShoppingId}
            selectedId={selectedShoppingId}
            reloadKey={listVersion}
            onGenerated={(id) => {
              refreshList();
              setSelectedShoppingId(id);
            }}
          />
        )}
      </aside>
      <main className="main">
        {view === "settings" ? (
          <Settings />
        ) : view === "calendar" ? (
          <WeekCalendar reloadKey={listVersion} />
        ) : view === "shopping" ? (
          selectedShoppingId == null ? (
            <div className="empty">
              <h2>Shopping lists</h2>
              <p className="muted">
                Generate a list from a planned week on the left, then check items off as
                you shop. Quantities are summed across every meal in the week.
              </p>
            </div>
          ) : (
            <ShoppingListDetail
              listId={selectedShoppingId}
              onChanged={refreshList}
              onDeleted={() => {
                refreshList();
                setSelectedShoppingId(null);
              }}
            />
          )
        ) : creating ? (
          <NewRecipe
            onCreated={(id) => {
              setCreating(false);
              refreshList();
              setSelectedId(id);
            }}
            onCancel={() => setCreating(false)}
          />
        ) : selectedId == null ? (
          <div className="empty">
            <h2>Select a recipe</h2>
            <p className="muted">
              Click <strong>+ New recipe</strong> to add one by hand, paste a recipe
              page or video link to import one, or pick a recipe on the left to see its
              macro breakdown.
            </p>
          </div>
        ) : (
          <RecipeDetail
            recipeId={selectedId}
            onChanged={refreshList}
            onDeleted={() => {
              refreshList();
              setSelectedId(null);
            }}
          />
        )}
      </main>
    </div>
  );
}

export default App;
