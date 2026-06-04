"""Export API tests — the Google adapter is replaced by an in-memory fake, so
no OAuth/network happens. Exercises the use-case + router + persistence wiring."""

from recetario.application.ports.export import ExportResult


class FakeExporter:
    def __init__(self, connected=True):
        self._connected = connected
        self.exported = []

    def is_connected(self):
        return self._connected

    def connect(self):
        self._connected = True

    def export(self, shopping_list, *, tasklist_id):
        self.exported.append(shopping_list.id)
        ids = {i.id: f"task-{i.id}" for i in shopping_list.items if i.id is not None}
        return ExportResult(tasklist_id=tasklist_id or "tasklist-1", item_task_ids=ids)


def _use_exporter(client, exporter):
    client.app.state.task_exporter_factory = lambda session: exporter


def _list_with_items(client):
    recipe = client.post(
        "/recipes",
        json={
            "title": "Onion soup",
            "servings": 2,
            "ingredients": [{"name": "Onion", "quantity": "2", "unit": "pc"}],
        },
    ).json()
    client.post(
        "/meals",
        json={"date": "2026-06-02", "meal_type": "dinner", "recipe_id": recipe["id"]},
    )
    return client.post(
        "/shopping-lists", json={"week_start": "2026-06-01", "week_end": "2026-06-07"}
    ).json()


def test_status_reflects_connection(client):
    _use_exporter(client, FakeExporter(connected=False))
    body = client.get("/integrations/google-tasks").json()
    assert body["provider"] == "google_tasks"
    assert body["connected"] is False
    assert isinstance(body["client_configured"], bool)


def test_export_when_connected_persists_ids_and_status(client):
    exporter = FakeExporter(connected=True)
    _use_exporter(client, exporter)
    sl = _list_with_items(client)

    resp = client.post(f"/shopping-lists/{sl['id']}/export")
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "exported"
    assert out["external_tasklist_id"] == "tasklist-1"
    item = out["items"][0]
    assert item["external_task_id"] == f"task-{item['id']}"
    assert exporter.exported == [sl["id"]]

    # Persisted: re-fetching shows the exported state + external ids.
    reloaded = client.get(f"/shopping-lists/{sl['id']}").json()
    assert reloaded["status"] == "exported"
    assert reloaded["items"][0]["external_task_id"] is not None


def test_reexport_reuses_stored_tasklist_id(client):
    exporter = FakeExporter(connected=True)
    _use_exporter(client, exporter)
    sl = _list_with_items(client)

    client.post(f"/shopping-lists/{sl['id']}/export")
    # Second export should pass the stored tasklist id back to the adapter.
    captured = {}
    original = exporter.export

    def spy(shopping_list, *, tasklist_id):
        captured["tasklist_id"] = tasklist_id
        return original(shopping_list, tasklist_id=tasklist_id)

    exporter.export = spy
    client.post(f"/shopping-lists/{sl['id']}/export")
    assert captured["tasklist_id"] == "tasklist-1"


def test_export_when_not_connected_is_409(client):
    _use_exporter(client, FakeExporter(connected=False))
    sl = _list_with_items(client)
    resp = client.post(f"/shopping-lists/{sl['id']}/export")
    assert resp.status_code == 409


def test_export_missing_list_404(client):
    _use_exporter(client, FakeExporter(connected=True))
    assert client.post("/shopping-lists/999/export").status_code == 404
