"""SQLAlchemy ORM models — the persistence schema.

Phase 1 covers the recipe/ingredient/tag core. Nutrition, meal-calendar, and
shopping-list tables are added in later phases (see DESIGN.md §2).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
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


Index("ix_recipes_title", RecipeModel.title)
UniqueConstraint(IngredientModel.normalized_name, name="uq_ingredients_normalized_name")
