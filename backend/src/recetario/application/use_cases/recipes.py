"""Recipe CRUD use cases.

Each interactor depends only on the RecipeRepository port. They translate input
DTOs into domain entities and delegate persistence to the repository.
"""

from __future__ import annotations

from recetario.application.dto import RecipeInput
from recetario.application.ports import RecipeRepository
from recetario.domain.entities import Ingredient, Recipe, RecipeIngredient, Tag


class RecipeNotFoundError(Exception):
    def __init__(self, recipe_id: int) -> None:
        super().__init__(f"Recipe {recipe_id} not found")
        self.recipe_id = recipe_id


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _to_domain(data: RecipeInput) -> Recipe:
    ingredients = [
        RecipeIngredient(
            ingredient=Ingredient(name=line.name.strip(), normalized_name=_normalize(line.name)),
            quantity=line.quantity,
            unit=line.unit,
            raw_text=line.raw_text,
            notes=line.notes,
            position=index,
        )
        for index, line in enumerate(data.ingredients)
    ]
    tags = [t.strip() for t in data.tags if t.strip()]
    return Recipe(
        title=data.title.strip(),
        description=data.description,
        source_url=data.source_url,
        source_type=data.source_type,
        servings=data.servings,
        rating=data.rating,
        status=data.status,
        instructions_md=data.instructions_md,
        ingredients=ingredients,
        tags=[Tag(name=t) for t in tags],
    )


class CreateRecipe:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    def __call__(self, data: RecipeInput) -> Recipe:
        return self._repo.add(_to_domain(data))


class GetRecipe:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    def __call__(self, recipe_id: int) -> Recipe:
        recipe = self._repo.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(recipe_id)
        return recipe


class ListRecipes:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    def __call__(self, *, tag: str | None = None, search: str | None = None) -> list[Recipe]:
        return self._repo.list(tag=tag, search=search)


class UpdateRecipe:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    def __call__(self, recipe_id: int, data: RecipeInput) -> Recipe:
        entity = _to_domain(data)
        entity.id = recipe_id
        updated = self._repo.update(entity)
        if updated is None:
            raise RecipeNotFoundError(recipe_id)
        return updated


class DeleteRecipe:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    def __call__(self, recipe_id: int) -> None:
        if not self._repo.delete(recipe_id):
            raise RecipeNotFoundError(recipe_id)
