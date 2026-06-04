from decimal import Decimal


def _recipe(client):
    """2-serving recipe: 2 pc onion + salt-to-taste (no quantity)."""
    return client.post(
        "/recipes",
        json={
            "title": "Onion soup",
            "servings": 2,
            "ingredients": [
                {"name": "Onion", "quantity": "2", "unit": "pc"},
                {"name": "Salt"},
            ],
        },
    ).json()


def _schedule(client, recipe_id, date, servings="2"):
    return client.post(
        "/meals",
        json={
            "date": date,
            "meal_type": "dinner",
            "recipe_id": recipe_id,
            "servings_planned": servings,
        },
    ).json()


def test_generate_aggregates_week_ingredients(client):
    recipe = _recipe(client)
    # Two dinners, each 2 servings (= recipe yield → factor 1, so 2 pc onion each).
    _schedule(client, recipe["id"], "2026-06-01")
    _schedule(client, recipe["id"], "2026-06-03")

    resp = client.post(
        "/shopping-lists",
        json={"week_start": "2026-06-01", "week_end": "2026-06-07"},
    )
    assert resp.status_code == 201, resp.text
    sl = resp.json()
    assert sl["status"] == "draft"
    items = {i["ingredient_name"]: i for i in sl["items"]}

    assert Decimal(items["Onion"]["total_quantity"]) == Decimal("4")  # 2 + 2
    assert items["Onion"]["unit"] == "pc"
    assert len(items["Onion"]["source_event_ids"]) == 2
    # Quantity-less ingredient is still listed.
    assert items["Salt"]["total_quantity"] is None
    assert items["Salt"]["checked"] is False


def test_scales_by_planned_servings(client):
    recipe = _recipe(client)
    # 1 serving of a 2-serving recipe → factor 0.5 → 1 pc onion.
    _schedule(client, recipe["id"], "2026-06-02", servings="1")
    sl = client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()
    onion = next(i for i in sl["items"] if i["ingredient_name"] == "Onion")
    assert Decimal(onion["total_quantity"]) == Decimal("1")


def test_check_off_item(client):
    recipe = _recipe(client)
    _schedule(client, recipe["id"], "2026-06-02")
    sl = client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()
    item_id = sl["items"][0]["id"]

    patched = client.patch(
        f"/shopping-lists/{sl['id']}/items/{item_id}", json={"checked": True}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["checked"] is True

    # Persisted: reloading the list reflects the checked item.
    reloaded = client.get(f"/shopping-lists/{sl['id']}").json()
    assert next(i for i in reloaded["items"] if i["id"] == item_id)["checked"] is True


def test_list_summary_counts(client):
    recipe = _recipe(client)
    _schedule(client, recipe["id"], "2026-06-02")
    sl = client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()
    client.patch(
        f"/shopping-lists/{sl['id']}/items/{sl['items'][0]['id']}", json={"checked": True}
    )

    summaries = client.get("/shopping-lists").json()
    assert len(summaries) == 1
    assert summaries[0]["item_count"] == 2
    assert summaries[0]["checked_count"] == 1


def test_empty_week_makes_empty_list(client):
    sl = client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()
    assert sl["items"] == []


def test_delete_shopping_list(client):
    recipe = _recipe(client)
    _schedule(client, recipe["id"], "2026-06-02")
    sl = client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()
    assert client.delete(f"/shopping-lists/{sl['id']}").status_code == 204
    assert client.get(f"/shopping-lists/{sl['id']}").status_code == 404


def test_rejects_inverted_range(client):
    resp = client.post(
        "/shopping-lists", json={"week_start": "2026-06-07", "week_end": "2026-06-01"}
    )
    assert resp.status_code == 422


def test_toggle_missing_item_404(client):
    resp = client.patch("/shopping-lists/1/items/999", json={"checked": True})
    assert resp.status_code == 404
