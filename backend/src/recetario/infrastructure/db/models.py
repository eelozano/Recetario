"""SQLAlchemy ORM models — the persistence schema.

Phase 1 covers the recipe/ingredient/tag core. Nutrition, meal-calendar, and
shopping-list tables are added in later phases (see DESIGN.md §2).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy import Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recetario.infrastructure.db.base import Base, TimestampMixin

recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class RecipeModel(TimestampMixin, Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), default="manual")
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    instructions_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    ingredients: Mapped[list["RecipeIngredientModel"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredientModel.position",
    )
    tags: Mapped[list["TagModel"]] = relationship(secondary=recipe_tags, back_populates="recipes")


class IngredientModel(TimestampMixin, Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    usda_fdc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)


class RecipeIngredientModel(TimestampMixin, Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    usda_fdc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gram_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recipe: Mapped[RecipeModel] = relationship(back_populates="ingredients")
    ingredient: Mapped[IngredientModel] = relationship(lazy="joined")


class TagModel(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)

    recipes: Mapped[list[RecipeModel]] = relationship(secondary=recipe_tags, back_populates="tags")


class IngestionJobModel(TimestampMixin, Base):
    """A recipe-import job (scrape a URL → draft recipe). Decouples the UI from
    long-running parse work; the UI polls `status` until succeeded/failed."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    input_url: Mapped[str] = mapped_column(String(2048))
    input_type: Mapped[str] = mapped_column(String(16), default="web")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    # SET NULL (not CASCADE): deleting the produced recipe shouldn't erase job history.
    result_recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MealEventModel(TimestampMixin, Base):
    """A scheduled recipe in a meal slot on a date (Phase 4). A week's plan is a
    date-range query over this table; no separate week entity."""

    __tablename__ = "meal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date: Mapped[Date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(String(16))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    servings_planned: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(1))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recipe: Mapped[RecipeModel] = relationship(lazy="joined")


class ShoppingListModel(TimestampMixin, Base):
    """A week's aggregated grocery list (Phase 5). Persisted so check-off state
    and Google Tasks export ids (Phase 6) survive across sessions."""

    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    week_start: Mapped[Date] = mapped_column(Date)
    week_end: Mapped[Date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")

    items: Mapped[list["ShoppingListItemModel"]] = relationship(
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        order_by="ShoppingListItemModel.id",
    )


class ShoppingListItemModel(TimestampMixin, Base):
    __tablename__ = "shopping_list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    shopping_list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE")
    )
    # Denormalized name (+ optional catalog id) so the list renders without a join.
    ingredient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingredient_name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    external_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_event_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    shopping_list: Mapped[ShoppingListModel] = relationship(back_populates="items")


# --- USDA FoodData Central cache (Phase 2) -----------------------------------
# A local subset of FDC, populated by the seeder. Nutrient amounts are stored on
# a per-100g basis (the FDC convention for SR Legacy / Foundation foods), which
# the MacroCalculator scales by each line's gram_weight.


class NutrientModel(TimestampMixin, Base):
    """Reference table of the nutrients we track (calories, protein, fat, …)."""

    __tablename__ = "nutrients"

    id: Mapped[int] = mapped_column(primary_key=True)
    usda_nutrient_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16))


class UsdaFoodModel(TimestampMixin, Base):
    __tablename__ = "usda_foods"

    # fdc_id is FDC's own stable identifier — use it directly as the PK.
    fdc_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    description: Mapped[str] = mapped_column(String(512))
    data_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)

    nutrients: Mapped[list["UsdaFoodNutrientModel"]] = relationship(
        back_populates="food", cascade="all, delete-orphan"
    )
    portions: Mapped[list["UsdaFoodPortionModel"]] = relationship(
        back_populates="food", cascade="all, delete-orphan"
    )


class UsdaFoodNutrientModel(TimestampMixin, Base):
    __tablename__ = "usda_food_nutrients"

    id: Mapped[int] = mapped_column(primary_key=True)
    fdc_id: Mapped[int] = mapped_column(ForeignKey("usda_foods.fdc_id", ondelete="CASCADE"))
    nutrient_id: Mapped[int] = mapped_column(ForeignKey("nutrients.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4))  # per 100 g
    unit_name: Mapped[str | None] = mapped_column(String(16), nullable=True)

    food: Mapped[UsdaFoodModel] = relationship(back_populates="nutrients")
    nutrient: Mapped[NutrientModel] = relationship(lazy="joined")


class UsdaFoodPortionModel(TimestampMixin, Base):
    __tablename__ = "usda_food_portions"

    id: Mapped[int] = mapped_column(primary_key=True)
    fdc_id: Mapped[int] = mapped_column(ForeignKey("usda_foods.fdc_id", ondelete="CASCADE"))
    portion_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    gram_weight: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    food: Mapped[UsdaFoodModel] = relationship(back_populates="portions")


Index("ix_recipes_title", RecipeModel.title)
Index("ix_meal_events_date", MealEventModel.date)
Index("ix_usda_foods_description", UsdaFoodModel.description)
Index(
    "ix_usda_food_nutrients_fdc_nutrient",
    UsdaFoodNutrientModel.fdc_id,
    UsdaFoodNutrientModel.nutrient_id,
    unique=True,
)
