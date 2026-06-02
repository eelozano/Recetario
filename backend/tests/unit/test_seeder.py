from decimal import Decimal

from recetario.application.dto.nutrition_dto import FoodDetail, FoodNutrient, FoodSummary
from recetario.infrastructure.nutrition.seeder import seed_foods


class FakeProvider:
    def __init__(self, foods: dict[str, FoodDetail]):
        self._foods = foods  # keyed by query string

    def search(self, query, *, page_size=5):
        food = self._foods.get(query)
        return [FoodSummary(fdc_id=food.fdc_id, description=food.description)] if food else []

    def get_food(self, fdc_id):
        for food in self._foods.values():
            if food.fdc_id == fdc_id:
                return food
        return None


class FakeRepo:
    def __init__(self):
        self.upserts: list[int] = []

    def upsert_food(self, detail):
        self.upserts.append(detail.fdc_id)


def _detail(fdc_id, desc):
    return FoodDetail(
        fdc_id=fdc_id,
        description=desc,
        nutrients=[FoodNutrient(1008, "calories", "kcal", Decimal("40"))],
    )


def test_seed_foods_caches_top_hits():
    provider = FakeProvider({"onion": _detail(1, "Onion"), "garlic": _detail(2, "Garlic")})
    repo = FakeRepo()

    result = seed_foods(provider, repo, names=("onion", "garlic"))

    assert result.seeded == ["onion", "garlic"]
    assert repo.upserts == [1, 2]


def test_seed_foods_skips_unmatched_queries():
    provider = FakeProvider({"onion": _detail(1, "Onion")})
    repo = FakeRepo()

    result = seed_foods(provider, repo, names=("onion", "unobtanium"))

    assert result.seeded == ["onion"]
    assert result.skipped == ["unobtanium"]
    assert repo.upserts == [1]
