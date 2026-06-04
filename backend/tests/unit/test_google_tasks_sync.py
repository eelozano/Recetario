from decimal import Decimal

from recetario.domain.entities import ShoppingList, ShoppingListItem
from recetario.infrastructure.export import sync_list, task_title


class FakeTasksClient:
    """In-memory stand-in for the Google Tasks API — exercises sync_list's
    idempotency logic without any network."""

    def __init__(self):
        self.lists: dict[str, str] = {}
        self.tasks: dict[tuple[str, str], dict] = {}
        self._lc = 0
        self._tc = 0

    def ensure_task_list(self, title, tasklist_id):
        if tasklist_id and tasklist_id in self.lists:
            self.lists[tasklist_id] = title
            return tasklist_id
        self._lc += 1
        lid = f"L{self._lc}"
        self.lists[lid] = title
        return lid

    def upsert_task(self, tasklist_id, *, task_id, title, completed):
        status = "completed" if completed else "needsAction"
        if task_id and (tasklist_id, task_id) in self.tasks:
            self.tasks[(tasklist_id, task_id)] = {"title": title, "status": status}
            return task_id
        self._tc += 1
        tid = f"T{self._tc}"
        self.tasks[(tasklist_id, tid)] = {"title": title, "status": status}
        return tid


def _list(items, *, tasklist_id=None):
    from datetime import date

    return ShoppingList(
        name="Groceries",
        week_start=date(2026, 6, 1),
        week_end=date(2026, 6, 7),
        items=items,
        external_tasklist_id=tasklist_id,
    )


def test_first_export_creates_list_and_tasks():
    client = FakeTasksClient()
    sl = _list(
        [
            ShoppingListItem(id=1, ingredient_name="Onion", unit="pc", total_quantity=Decimal(4)),
            ShoppingListItem(id=2, ingredient_name="Salt"),
        ]
    )
    result = sync_list(client, sl, None)

    assert result.tasklist_id in client.lists
    assert len(client.tasks) == 2
    assert set(result.item_task_ids) == {1, 2}


def test_reexport_is_idempotent():
    client = FakeTasksClient()
    sl = _list(
        [ShoppingListItem(id=1, ingredient_name="Onion", unit="pc", total_quantity=Decimal(4))]
    )
    first = sync_list(client, sl, None)

    # Simulate the persisted ids being fed back in on the next run.
    sl.external_tasklist_id = first.tasklist_id
    sl.items[0].external_task_id = first.item_task_ids[1]
    sl.items[0].checked = True

    second = sync_list(client, sl, sl.external_tasklist_id)

    # No new list, no new task — same ids reused.
    assert second.tasklist_id == first.tasklist_id
    assert second.item_task_ids[1] == first.item_task_ids[1]
    assert len(client.lists) == 1
    assert len(client.tasks) == 1
    # Checked item became a completed task.
    key = (second.tasklist_id, second.item_task_ids[1])
    assert client.tasks[key]["status"] == "completed"


def test_recreates_task_when_external_id_is_stale():
    client = FakeTasksClient()
    sl = _list(
        [ShoppingListItem(id=1, ingredient_name="Onion", external_task_id="ghost")],
        tasklist_id=None,
    )
    result = sync_list(client, sl, None)
    # "ghost" wasn't a real task → a fresh one is created.
    assert result.item_task_ids[1] != "ghost"
    assert len(client.tasks) == 1


def test_task_title_formatting():
    assert (
        task_title(ShoppingListItem(id=1, ingredient_name="Onion", unit="pc", total_quantity=Decimal(4)))
        == "Onion — 4 pc"
    )
    assert task_title(ShoppingListItem(id=2, ingredient_name="Salt")) == "Salt"
    # Trailing zeros trimmed.
    assert (
        task_title(
            ShoppingListItem(id=3, ingredient_name="Flour", unit="cup", total_quantity=Decimal("0.500"))
        )
        == "Flour — 0.5 cup"
    )
