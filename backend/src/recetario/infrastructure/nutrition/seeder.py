"""Seed the local USDA FDC cache with a curated set of common ingredients.

Run once (needs a free FDC API key) to populate usda_foods / nutrients /
usda_food_nutrients / usda_food_portions so the app can compute macros offline:

    RECETARIO_FDC_API_KEY=xxxx python -m recetario.infrastructure.nutrition.seeder

The seeding *logic* (`seed_foods`) is decoupled from the concrete adapters so it
can be unit-tested with a fake provider. `main()` is the composition root that
wires the live FDC client + SQLAlchemy repository.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from recetario.application.ports import NutritionProvider, NutritionRepository

logger = logging.getLogger("recetario.seeder")

# ~50 generic, single-ingredient foods covering most everyday recipes.
COMMON_INGREDIENTS: tuple[str, ...] = (
    "onion raw",
    "garlic raw",
    "tomato raw",
    "olive oil",
    "salt table",
    "black pepper",
    "chicken breast raw",
    "ground beef raw",
    "white rice cooked",
    "spaghetti cooked",
    "egg whole raw",
    "milk whole",
    "butter salted",
    "wheat flour white all-purpose",
    "sugar granulated",
    "brown sugar",
    "carrot raw",
    "celery raw",
    "potato raw",
    "sweet potato raw",
    "bell pepper red raw",
    "broccoli raw",
    "spinach raw",
    "mushroom white raw",
    "cheddar cheese",
    "parmesan cheese",
    "mozzarella cheese",
    "lemon raw",
    "lime raw",
    "banana raw",
    "apple raw",
    "avocado raw",
    "black beans cooked",
    "chickpeas cooked",
    "lentils cooked",
    "tomatoes canned",
    "chicken broth",
    "soy sauce",
    "honey",
    "oats rolled dry",
    "almonds raw",
    "walnuts",
    "peanut butter",
    "yogurt plain whole milk",
    "cucumber raw",
    "zucchini raw",
    "green beans raw",
    "corn sweet yellow raw",
    "salmon atlantic raw",
    "shrimp raw",
    "tofu firm",
    "bread white",
)


@dataclass
class SeedResult:
    seeded: list[str]
    skipped: list[str]

    @property
    def summary(self) -> str:
        return f"seeded {len(self.seeded)}, skipped {len(self.skipped)}"


def seed_foods(
    provider: NutritionProvider,
    repository: NutritionRepository,
    names: tuple[str, ...] = COMMON_INGREDIENTS,
) -> SeedResult:
    """For each query, take the top FDC hit, fetch detail, and cache it."""
    seeded: list[str] = []
    skipped: list[str] = []

    for name in names:
        hits = provider.search(name, page_size=1)
        if not hits:
            logger.warning("no FDC match for %r", name)
            skipped.append(name)
            continue

        detail = provider.get_food(hits[0].fdc_id)
        if detail is None or not detail.nutrients:
            logger.warning("no usable detail for %r (fdc_id=%s)", name, hits[0].fdc_id)
            skipped.append(name)
            continue

        repository.upsert_food(detail)
        logger.info("cached %r → %s (%s)", name, detail.description, detail.fdc_id)
        seeded.append(name)

    return SeedResult(seeded=seeded, skipped=skipped)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from recetario.infrastructure.config import get_settings
    from recetario.infrastructure.db.repositories import SqlAlchemyNutritionRepository
    from recetario.infrastructure.db.session import create_db_engine, create_session_factory
    from recetario.infrastructure.nutrition.fdc_client import UsdaFdcClient

    settings = get_settings()
    if not settings.fdc_api_key:
        logger.error("RECETARIO_FDC_API_KEY is not set. Get a free key at "
                     "https://fdc.nal.usda.gov/api-key-signup.html")
        return 1

    engine = create_db_engine(settings)
    session = create_session_factory(engine)()
    try:
        repository = SqlAlchemyNutritionRepository(session)
        with UsdaFdcClient(settings.fdc_api_key) as provider:
            result = seed_foods(provider, repository)
    finally:
        session.close()

    logger.info("Done: %s", result.summary)
    if result.skipped:
        logger.info("Skipped: %s", ", ".join(result.skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
