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
                nutrients=[FoodNutrient(1008, "calories", "kcal", Decimal("40"))],
            )
        )
    finally:
        session.close()


def _linked_recipe(client):
    """A 2-serving recipe whose single onion line is linked → 80 kcal total, 40/serving."""
    recipe = client.post(
        "/recipes",
        json={
            "title": "Onion soup",
            "servings": 2,
            "ingredients": [{"name": "Onion", "quantity": "1", "unit": "pc"}],
        },
    ).json()
    client.post(
        f"/recipes/{recipe['id']}/ingredients/0/link",
        json={"fdc_id": 170000, "gram_weight": "200"},
    )
    return recipe


def test_schedule_and_week_plan_with_macros(client):
    _seed_onion(client)
    recipe = _linked_recipe(client)

    created = client.post(
        "/meals",
        json={
            "date": "2026-06-01",
            "meal_type": "dinner",
            "recipe_id": recipe["id"],
            "servings_planned": "2",
        },
    )
    assert created.status_code == 201, created.text
    event = created.json()
    assert event["recipe_title"] == "Onion soup"
    assert event["meal_type"] == "dinner"

    plan = client.get("/meals", params={"start": "2026-06-01", "end": "2026-06-07"})
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert len(body["events"]) == 1
    # 40 kcal/serving * 2 servings planned = 80
    assert Decimal(body["macros"]["totals"]["calories"]) == Decimal("80")
    assert len(body["macros"]["days"]) == 1
    assert body["macros"]["days"][0]["date"] == "2026-06-01"
    assert Decimal(body["macros"]["days"][0]["totals"]["calories"]) == Decimal("80")


def test_week_plan_excludes_out_of_range_events(client):
    _seed_onion(client)
    recipe = _linked_recipe(client)
    for d in ("2026-06-01", "2026-06-20"):
        client.post(
            "/meals",
            json={"date": d, "meal_type": "lunch", "recipe_id": recipe["id"], "servings_planned": "1"},
        )

    plan = client.get("/meals", params={"start": "2026-06-01", "end": "2026-06-07"}).json()
    assert len(plan["events"]) == 1
    assert Decimal(plan["macros"]["totals"]["calories"]) == Decimal("40")


def test_schedule_unknown_recipe_returns_404(client):
    resp = client.post(
        "/meals",
        json={"date": "2026-06-01", "meal_type": "dinner", "recipe_id": 999},
    )
    assert resp.status_code == 404


def test_update_and_delete_meal(client):
    _seed_onion(client)
    recipe = _linked_recipe(client)
    event = client.post(
        "/meals",
        json={"date": "2026-06-01", "meal_type": "dinner", "recipe_id": recipe["id"]},
    ).json()

    updated = client.put(
        f"/meals/{event['id']}",
        json={
            "date": "2026-06-02",
            "meal_type": "lunch",
            "recipe_id": recipe["id"],
            "servings_planned": "3",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["meal_type"] == "lunch"
    assert Decimal(updated.json()["servings_planned"]) == Decimal("3")

    assert client.delete(f"/meals/{event['id']}").status_code == 204
    assert client.get(f"/meals/{event['id']}").status_code == 404


def test_deleting_recipe_cascades_to_meal_events(client):
    _seed_onion(client)
    recipe = _linked_recipe(client)
    event = client.post(
        "/meals",
        json={"date": "2026-06-01", "meal_type": "dinner", "recipe_id": recipe["id"]},
    ).json()

    assert client.delete(f"/recipes/{recipe['id']}").status_code == 204
    assert client.get(f"/meals/{event['id']}").status_code == 404


def test_week_plan_rejects_inverted_range(client):
    resp = client.get("/meals", params={"start": "2026-06-07", "end": "2026-06-01"})
    assert resp.status_code == 422
