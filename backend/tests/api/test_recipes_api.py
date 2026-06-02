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
