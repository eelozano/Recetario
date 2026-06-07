"""SQLAlchemy adapter implementing the RecipeRepository / TagRepository ports.

This is the only place that knows about both the ORM and the domain entities.
Mapping is explicit (ORM row ↔ domain object) so the domain stays persistence-free.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from recetario.domain.entities import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeStatus,
    SourceType,
    Tag,
)
from recetario.identity import DEFAULT_OWNER_ID
from recetario.infrastructure.db.models import (
    IngredientModel,
    RecipeIngredientModel,
    RecipeModel,
    TagModel,
)


def _ingredient_to_domain(model: IngredientModel) -> Ingredient:
    return Ingredient(
        id=model.id,
        name=model.name,
        normalized_name=model.normalized_name,
        usda_fdc_id=model.usda_fdc_id,
        default_unit=model.default_unit,
    )


def _recipe_to_domain(model: RecipeModel) -> Recipe:
    return Recipe(
        id=model.id,
        title=model.title,
        description=model.description,
        source_url=model.source_url,
        source_type=SourceType(model.source_type),
        servings=model.servings,
        rating=model.rating,
        status=RecipeStatus(model.status),
        instructions_md=model.instructions_md,
        calories_per_serving=model.calories_per_serving,
        protein_per_serving=model.protein_per_serving,
        fat_per_serving=model.fat_per_serving,
        carbs_per_serving=model.carbs_per_serving,
        fiber_per_serving=model.fiber_per_serving,
        sodium_per_serving=model.sodium_per_serving,
        ingredients=[
            RecipeIngredient(
                id=ri.id,
                ingredient=_ingredient_to_domain(ri.ingredient),
                quantity=ri.quantity,
                unit=ri.unit,
                raw_text=ri.raw_text,
                position=ri.position,
                usda_fdc_id=ri.usda_fdc_id,
                gram_weight=ri.gram_weight,
                notes=ri.notes,
            )
            for ri in model.ingredients
        ],
        tags=[Tag(id=t.id, name=t.name) for t in model.tags],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyRecipeRepository:
    def __init__(self, session: Session, *, owner_id: int = DEFAULT_OWNER_ID) -> None:
        self._session = session
        self._owner_id = owner_id

    def _get_or_create_ingredient(self, ingredient: Ingredient) -> IngredientModel:
        existing = self._session.scalar(
            select(IngredientModel).where(
                IngredientModel.normalized_name == ingredient.normalized_name
            )
        )
        if existing is not None:
            return existing
        model = IngredientModel(
            name=ingredient.name,
            normalized_name=ingredient.normalized_name,
            default_unit=ingredient.default_unit,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def _get_or_create_tag(self, name: str) -> TagModel:
        existing = self._session.scalar(select(TagModel).where(TagModel.name == name))
        if existing is not None:
            return existing
        model = TagModel(name=name)
        self._session.add(model)
        self._session.flush()
        return model

    def _apply(self, model: RecipeModel, recipe: Recipe) -> None:
        model.title = recipe.title
        model.description = recipe.description
        model.source_url = recipe.source_url
        model.source_type = recipe.source_type.value
        model.servings = recipe.servings
        model.rating = recipe.rating
        model.status = recipe.status.value
        model.instructions_md = recipe.instructions_md
        model.calories_per_serving = recipe.calories_per_serving
        model.protein_per_serving = recipe.protein_per_serving
        model.fat_per_serving = recipe.fat_per_serving
        model.carbs_per_serving = recipe.carbs_per_serving
        model.fiber_per_serving = recipe.fiber_per_serving
        model.sodium_per_serving = recipe.sodium_per_serving
        model.ingredients = [
            RecipeIngredientModel(
                ingredient=self._get_or_create_ingredient(line.ingredient),
                position=line.position,
                raw_text=line.raw_text,
                quantity=line.quantity,
                unit=line.unit,
                usda_fdc_id=line.usda_fdc_id,
                gram_weight=line.gram_weight,
                notes=line.notes,
            )
            for line in recipe.ingredients
        ]
        model.tags = [self._get_or_create_tag(t.name) for t in recipe.tags]

    def add(self, recipe: Recipe) -> Recipe:
        model = RecipeModel(owner_id=self._owner_id)
        self._apply(model, recipe)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _recipe_to_domain(model)

    def _load(self, recipe_id: int) -> RecipeModel | None:
        return self._session.scalar(
            select(RecipeModel)
            .where(RecipeModel.id == recipe_id, RecipeModel.owner_id == self._owner_id)
            .options(selectinload(RecipeModel.ingredients), selectinload(RecipeModel.tags))
        )

    def get(self, recipe_id: int) -> Recipe | None:
        model = self._load(recipe_id)
        return _recipe_to_domain(model) if model else None

    def list(self, *, tag: str | None = None, search: str | None = None) -> list[Recipe]:
        stmt = (
            select(RecipeModel)
            .where(RecipeModel.owner_id == self._owner_id)
            .options(selectinload(RecipeModel.ingredients), selectinload(RecipeModel.tags))
            .order_by(RecipeModel.created_at.desc())
        )
        if search:
            stmt = stmt.where(RecipeModel.title.ilike(f"%{search}%"))
        if tag:
            stmt = stmt.join(RecipeModel.tags).where(TagModel.name == tag)
        return [_recipe_to_domain(m) for m in self._session.scalars(stmt).unique()]

    def update(self, recipe: Recipe) -> Recipe | None:
        assert recipe.id is not None
        model = self._load(recipe.id)
        if model is None:
            return None
        self._apply(model, recipe)
        self._session.commit()
        self._session.refresh(model)
        return _recipe_to_domain(model)

    def delete(self, recipe_id: int) -> bool:
        model = self._load(recipe_id)  # owner-scoped
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True


class SqlAlchemyTagRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[Tag]:
        rows = self._session.scalars(select(TagModel).order_by(TagModel.name))
        return [Tag(id=t.id, name=t.name) for t in rows]
