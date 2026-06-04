"""Composition root — wires concrete adapters into the API via FastAPI Depends.

The engine/session factory lives on app.state so tests can swap in an in-memory DB
by overriding `get_session`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from recetario.application.ports import TaskExporter
from recetario.identity import DEFAULT_OWNER_ID
from recetario.application.use_cases.export import ConnectGoogleTasks, ExportShoppingListToTasks
from recetario.application.use_cases.ingestion import (
    GetIngestionJob,
    ListIngestionJobs,
    StartUrlIngestion,
)
from recetario.application.use_cases.meal import (
    CalculateWeekMacros,
    DeleteMealEvent,
    GetMealEvent,
    ListWeek,
    ScheduleMeal,
    UpdateMealEvent,
)
from recetario.application.use_cases.nutrition import (
    CalculateRecipeMacros,
    LinkRecipeIngredientToUsda,
    SearchCachedFoods,
)
from recetario.application.use_cases.shopping import (
    DeleteShoppingList,
    GenerateWeeklyShoppingList,
    GetShoppingList,
    ListShoppingLists,
    ToggleShoppingItem,
)
from recetario.application.use_cases.recipes import (
    CreateRecipe,
    DeleteRecipe,
    GetRecipe,
    ListRecipes,
    UpdateRecipe,
)
from recetario.domain.services.macro_calculator import MacroCalculator
from recetario.domain.services.meal_planner import MealPlanAggregator
from recetario.domain.services.shopping_aggregator import ShoppingAggregator
from recetario.infrastructure.db.repositories import (
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyMealEventRepository,
    SqlAlchemyNutritionRepository,
    SqlAlchemyRecipeRepository,
    SqlAlchemyShoppingListRepository,
    SqlAlchemyTagRepository,
)


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_owner_id(request: Request) -> int:
    """Resolve the owner the current request acts on.

    Single-user today: every request is the implicit default owner. This is the
    one and only place that knowledge lives — when real auth arrives, resolve the
    authenticated principal here (from a header/session/token) and the entire
    stack becomes multi-tenant with no other changes. An override on app.state
    lets tests exercise a second owner.
    """
    return getattr(request.app.state, "owner_id", DEFAULT_OWNER_ID)


def get_recipe_repository(
    session: Session = Depends(get_session),
    owner_id: int = Depends(get_owner_id),
) -> SqlAlchemyRecipeRepository:
    return SqlAlchemyRecipeRepository(session, owner_id=owner_id)


def get_tag_repository(session: Session = Depends(get_session)) -> SqlAlchemyTagRepository:
    return SqlAlchemyTagRepository(session)


def get_nutrition_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyNutritionRepository:
    return SqlAlchemyNutritionRepository(session)


def get_ingestion_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyIngestionJobRepository:
    return SqlAlchemyIngestionJobRepository(session)


def get_meal_repository(
    session: Session = Depends(get_session),
    owner_id: int = Depends(get_owner_id),
) -> SqlAlchemyMealEventRepository:
    return SqlAlchemyMealEventRepository(session, owner_id=owner_id)


def get_shopping_repository(
    session: Session = Depends(get_session),
    owner_id: int = Depends(get_owner_id),
) -> SqlAlchemyShoppingListRepository:
    return SqlAlchemyShoppingListRepository(session, owner_id=owner_id)


def create_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return CreateRecipe(repo)


def get_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return GetRecipe(repo)


def list_recipes_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return ListRecipes(repo)


def update_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return UpdateRecipe(repo)


def delete_recipe_uc(repo: SqlAlchemyRecipeRepository = Depends(get_recipe_repository)):
    return DeleteRecipe(repo)


def calculate_macros_uc(
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> CalculateRecipeMacros:
    return CalculateRecipeMacros(recipes, nutrition, MacroCalculator())


def link_ingredient_uc(
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> LinkRecipeIngredientToUsda:
    return LinkRecipeIngredientToUsda(recipes, nutrition)


def search_foods_uc(
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> SearchCachedFoods:
    return SearchCachedFoods(nutrition)


def schedule_meal_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
) -> ScheduleMeal:
    return ScheduleMeal(meals, recipes)


def get_meal_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
) -> GetMealEvent:
    return GetMealEvent(meals)


def list_week_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
) -> ListWeek:
    return ListWeek(meals)


def update_meal_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
) -> UpdateMealEvent:
    return UpdateMealEvent(meals, recipes)


def delete_meal_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
) -> DeleteMealEvent:
    return DeleteMealEvent(meals)


def week_macros_uc(
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
    nutrition: SqlAlchemyNutritionRepository = Depends(get_nutrition_repository),
) -> CalculateWeekMacros:
    return CalculateWeekMacros(
        meals, recipes, nutrition, MacroCalculator(), MealPlanAggregator()
    )


def generate_shopping_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
    meals: SqlAlchemyMealEventRepository = Depends(get_meal_repository),
    recipes: SqlAlchemyRecipeRepository = Depends(get_recipe_repository),
) -> GenerateWeeklyShoppingList:
    return GenerateWeeklyShoppingList(lists, meals, recipes, ShoppingAggregator())


def get_shopping_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
) -> GetShoppingList:
    return GetShoppingList(lists)


def list_shopping_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
) -> ListShoppingLists:
    return ListShoppingLists(lists)


def delete_shopping_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
) -> DeleteShoppingList:
    return DeleteShoppingList(lists)


def toggle_item_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
) -> ToggleShoppingItem:
    return ToggleShoppingItem(lists)


def get_task_exporter(
    request: Request, session: Session = Depends(get_session)
) -> TaskExporter:
    # The factory lives on app.state so tests can swap in a fake (no Google/network).
    return request.app.state.task_exporter_factory(session)


def connect_google_uc(exporter: TaskExporter = Depends(get_task_exporter)) -> ConnectGoogleTasks:
    return ConnectGoogleTasks(exporter)


def export_shopping_uc(
    lists: SqlAlchemyShoppingListRepository = Depends(get_shopping_repository),
    exporter: TaskExporter = Depends(get_task_exporter),
) -> ExportShoppingListToTasks:
    return ExportShoppingListToTasks(lists, exporter)


def start_ingestion_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> StartUrlIngestion:
    return StartUrlIngestion(jobs)


def get_ingestion_job_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> GetIngestionJob:
    return GetIngestionJob(jobs)


def list_ingestion_jobs_uc(
    jobs: SqlAlchemyIngestionJobRepository = Depends(get_ingestion_repository),
) -> ListIngestionJobs:
    return ListIngestionJobs(jobs)
