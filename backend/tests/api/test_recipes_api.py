def _sample_recipe():
    return {
        "title": "Tomato Pasta",
        "servings": 2,
        "rating": 4,
        "status": "finalized",
        "instructions_md": "Boil pasta. Add sauce.",
        "ingredients": [
            {"name": "Spaghetti", "quantity": "200", "unit": "g"},
            {"name": "Canned Tomatoes", "quantity": "400", "unit": "g"},
        ],
        "tags": ["dinner", "quick"],
    }


def test_create_and_get_recipe(client):
    resp = client.post("/recipes", json=_sample_recipe())
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["title"] == "Tomato Pasta"
    assert len(created["ingredients"]) == 2
    assert {t["name"] for t in created["tags"]} == {"dinner", "quick"}

    recipe_id = created["id"]
    got = client.get(f"/recipes/{recipe_id}")
    assert got.status_code == 200
    assert got.json()["ingredients"][0]["name"] == "Spaghetti"


def test_list_filter_by_tag_and_search(client):
    client.post("/recipes", json=_sample_recipe())
    client.post(
        "/recipes",
        json={"title": "Oatmeal", "tags": ["breakfast"], "ingredients": []},
    )

    assert len(client.get("/recipes").json()) == 2
    assert len(client.get("/recipes", params={"tag": "dinner"}).json()) == 1
    assert client.get("/recipes", params={"search": "oat"}).json()[0]["title"] == "Oatmeal"


def test_update_recipe(client):
    recipe_id = client.post("/recipes", json=_sample_recipe()).json()["id"]
    payload = _sample_recipe()
    payload["title"] = "Tomato Pasta (v2)"
    payload["ingredients"] = [{"name": "Penne", "quantity": "250", "unit": "g"}]

    resp = client.put(f"/recipes/{recipe_id}", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Tomato Pasta (v2)"
    assert len(body["ingredients"]) == 1
    assert body["ingredients"][0]["name"] == "Penne"


def test_delete_recipe(client):
    recipe_id = client.post("/recipes", json=_sample_recipe()).json()["id"]
    assert client.delete(f"/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/recipes/{recipe_id}").status_code == 404


def test_get_missing_recipe_returns_404(client):
    assert client.get("/recipes/999").status_code == 404


def test_tags_endpoint(client):
    client.post("/recipes", json=_sample_recipe())
    names = {t["name"] for t in client.get("/tags").json()}
    assert {"dinner", "quick"} <= names


def test_manual_macros_round_trip_and_drive_breakdown(client):
    # Create a recipe with hand-entered per-serving macros (#18).
    payload = _sample_recipe()
    payload.update(
        servings=2,
        calories_per_serving="320",
        protein_per_serving="18",
        fat_per_serving="9",
        carbs_per_serving="40",
        fiber_per_serving="6",
        sodium_per_serving="450",
    )
    created = client.post("/recipes", json=payload).json()
    recipe_id = created["id"]

    # The values persist and come back on the recipe (as decimal strings).
    got = client.get(f"/recipes/{recipe_id}").json()
    assert got["calories_per_serving"] == "320.000"
    assert got["protein_per_serving"] == "18.000"
    assert got["sodium_per_serving"] == "450.000"

    # The macros endpoint reflects the manual values, not ingredient links.
    macros = client.get(f"/recipes/{recipe_id}/macros").json()
    assert macros["per_serving"]["calories"] == "320.000"
    assert macros["per_serving"]["carbohydrate"] == "40.000"
    # Totals scale by the 2-serving yield; no per-ingredient lines.
    assert macros["totals"]["calories"] == "640.000"
    assert macros["lines"] == []
    assert macros["unresolved_count"] == 0


def test_recipe_without_macros_leaves_fields_null(client):
    created = client.post("/recipes", json=_sample_recipe()).json()
    got = client.get(f"/recipes/{created['id']}").json()
    assert got["calories_per_serving"] is None
    assert got["sodium_per_serving"] is None


def test_negative_macro_is_rejected(client):
    payload = _sample_recipe()
    payload["calories_per_serving"] = "-5"
    assert client.post("/recipes", json=payload).status_code == 422
