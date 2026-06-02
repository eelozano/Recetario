from decimal import Decimal

from recetario.application.dto.nutrition_dto import FoodDetail, FoodNutrient
from recetario.infrastructure.db.repositories import SqlAlchemyNutritionRepository


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


def test_macros_unresolved_when_not_linked(client):
    recipe = _create_recipe(client)
    macros = client.get(f"/recipes/{recipe['id']}/macros").json()
    assert macros["totals"] == {}
    assert macros["unresolved_count"] == 1
    assert macros["lines"][0]["resolved"] is False


def test_link_to_uncached_food_is_rejected(client):
    recipe = _create_recipe(client)
    resp = client.post(
        f"/recipes/{recipe['id']}/ingredients/0/link",
        json={"fdc_id": 999999, "gram_weight": "100"},
    )
    assert resp.status_code == 422


def test_cached_food_search(client):
    _seed_onion(client)
    results = client.get("/foods/search", params={"query": "onion"}).json()
    assert results[0]["fdc_id"] == 170000


def test_macros_for_missing_recipe_returns_404(client):
    assert client.get("/recipes/999/macros").status_code == 404
