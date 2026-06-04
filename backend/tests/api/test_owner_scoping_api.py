"""Owner scoping through the full API stack (Phase 7).

The router/use-case/repo wiring resolves the owner via deps.get_owner_id, which
reads app.state.owner_id (defaulting to DEFAULT_OWNER_ID). Flipping that single
knob simulates a different authenticated principal — and proves the data is
already isolated end-to-end, so multi-user is an additive change.
"""

from __future__ import annotations


def _create_recipe(client, title: str) -> int:
    resp = client.post("/recipes", json={"title": title, "servings": 1, "ingredients": []})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_other_owner_cannot_see_or_fetch(client) -> None:
    rid = _create_recipe(client, "Default owner's recipe")  # owner = DEFAULT_OWNER_ID

    # Switch the resolved owner — same DB, different principal.
    client.app.state.owner_id = 999
    assert client.get("/recipes").json() == []
    assert client.get(f"/recipes/{rid}").status_code == 404
    assert client.delete(f"/recipes/{rid}").status_code == 404

    # Back to the real owner: the recipe is still there and untouched.
    client.app.state.owner_id = 1
    listing = client.get("/recipes").json()
    assert [r["title"] for r in listing] == ["Default owner's recipe"]
    assert client.get(f"/recipes/{rid}").status_code == 200
