from decimal import Decimal

from recetario.application.dto.nutrition_dto import FoodDetail, FoodNutrient, FoodSummary
from recetario.infrastructure.db.repositories import SqlAlchemyNutritionRepository


class _StubProvider:
    """A fake live FDC provider — returns canned data, never touches the network.

    Knows one food (fdc 555000, "Garlic, raw"); search echoes it for any query.
    """

    GARLIC = FoodDetail(
        fdc_id=555000,
        description="Garlic, raw",
        data_type="SR Legacy",
        nutrients=[FoodNutrient(1008, "calories", "kcal", Decimal("149"))],
    )

    def search(self, query, *, page_size=5):
        return [FoodSummary(fdc_id=555000, description="Garlic, raw", data_type="SR Legacy")]

    def get_food(self, fdc_id):
        return self.GARLIC if fdc_id == self.GARLIC.fdc_id else None


def _seed_onion(client):
    session = client.app.state.session_factory()
    try:
        SqlAlchemyNutritionRepository(session).upsert_food(
            FoodDetail(
                fdc_id=170000,
                description="Onions, raw",
                data_type="SR Legacy",
                category="Vegetables",
                nutrients=[
                    FoodNutrient(1008, "calories", "kcal", Decimal("40")),
                    FoodNutrient(1003, "protein", "g", Decimal("1.1")),
                ],
            )
        )
    finally:
        session.close()


def _create_recipe(client):
    return client.post(
        "/recipes",
        json={
            "title": "Onion soup",
            "servings": 2,
            "ingredients": [{"name": "Onion", "quantity": "1", "unit": "pc"}],
        },
    ).json()


def test_link_then_macros(client):
    _seed_onion(client)
    recipe = _create_recipe(client)
    position = recipe["ingredients"][0]["position"]

    link = client.post(
        f"/recipes/{recipe['id']}/ingredients/{position}/link",
        json={"fdc_id": 170000, "gram_weight": "200"},
    )
    assert link.status_code == 200, link.text
    assert link.json()["ingredients"][0]["usda_fdc_id"] == 170000

    macros = client.get(f"/recipes/{recipe['id']}/macros").json()
    assert Decimal(macros["totals"]["calories"]) == Decimal("80")
    assert Decimal(macros["totals"]["protein"]) == Decimal("2.2")
    assert Decimal(macros["per_serving"]["calories"]) == Decimal("40")
    assert macros["unresolved_count"] == 0
    assert macros["lines"][0]["resolved"] is True


def test_update_preserves_usda_links(client):
    _seed_onion(client)
    recipe = _create_recipe(client)
    position = recipe["ingredients"][0]["position"]

    linked = client.post(
        f"/recipes/{recipe['id']}/ingredients/{position}/link",
        json={"fdc_id": 170000, "gram_weight": "200"},
    ).json()
    line = linked["ingredients"][0]
    assert line["usda_fdc_id"] == 170000

    put = client.put(
        f"/recipes/{recipe['id']}",
        json={
            "title": "Onion soup",
            "servings": 2,
            "ingredients": [
                {
                    "name": line["name"],
                    "quantity": line["quantity"],
                    "unit": line["unit"],
                    "usda_fdc_id": line["usda_fdc_id"],
                    "gram_weight": line["gram_weight"],
                }
            ],
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["ingredients"][0]["usda_fdc_id"] == 170000
    assert Decimal(put.json()["ingredients"][0]["gram_weight"]) == Decimal("200")

    macros = client.get(f"/recipes/{recipe['id']}/macros").json()
    assert Decimal(macros["totals"]["calories"]) == Decimal("80")
    assert Decimal(macros["totals"]["protein"]) == Decimal("2.2")
    assert macros["unresolved_count"] == 0


def test_macros_unresolved_when_not_linked(client):
    recipe = _create_recipe(client)
    macros = client.get(f"/recipes/{recipe['id']}/macros").json()
    assert macros["totals"] == {}
    assert macros["unresolved_count"] == 1
    assert macros["lines"][0]["resolved"] is False


def test_link_to_uncached_food_is_rejected_without_provider(client):
    # Default conftest provider factory is `lambda: None` — no live FDC lookup.
    recipe = _create_recipe(client)
    resp = client.post(
        f"/recipes/{recipe['id']}/ingredients/0/link",
        json={"fdc_id": 999999, "gram_weight": "100"},
    )
    assert resp.status_code == 422


def test_link_caches_uncached_food_via_provider(client):
    # With a live provider, linking an uncached food fetches + caches it on the
    # fly, then resolves the line — so macros compute without pre-seeding.
    client.app.state.nutrition_provider_factory = lambda: _StubProvider()
    recipe = _create_recipe(client)
    position = recipe["ingredients"][0]["position"]

    link = client.post(
        f"/recipes/{recipe['id']}/ingredients/{position}/link",
        json={"fdc_id": 555000, "gram_weight": "100"},
    )
    assert link.status_code == 200, link.text
    assert link.json()["ingredients"][0]["usda_fdc_id"] == 555000

    macros = client.get(f"/recipes/{recipe['id']}/macros").json()
    assert Decimal(macros["totals"]["calories"]) == Decimal("149")  # 100 g of 149 kcal/100g
    assert macros["unresolved_count"] == 0


def test_link_to_food_unknown_to_provider_returns_404(client):
    client.app.state.nutrition_provider_factory = lambda: _StubProvider()
    recipe = _create_recipe(client)
    resp = client.post(
        f"/recipes/{recipe['id']}/ingredients/0/link",
        json={"fdc_id": 424242, "gram_weight": "100"},  # provider returns None
    )
    assert resp.status_code == 404


def test_cached_food_search(client):
    _seed_onion(client)
    results = client.get("/foods/search", params={"query": "onion"}).json()
    assert results[0]["fdc_id"] == 170000


def test_food_search_uses_live_provider_when_configured(client):
    # No cache seeded; results come from the live provider stub.
    client.app.state.nutrition_provider_factory = lambda: _StubProvider()
    results = client.get("/foods/search", params={"query": "garlic"}).json()
    assert [r["fdc_id"] for r in results] == [555000]


def test_macros_for_missing_recipe_returns_404(client):
    assert client.get("/recipes/999/macros").status_code == 404
