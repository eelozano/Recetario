"""Export use cases: connect the Google Tasks integration and sync a list.

The idempotent push lives in the TaskExporter adapter; these interactors handle
orchestration — load the list, require a connection, persist the returned
external ids + status.
"""

from __future__ import annotations

from recetario.application.ports import ShoppingListRepository, TaskExporter
from recetario.application.ports.export import NotConnectedError
from recetario.application.use_cases.shopping import ShoppingListNotFoundError
from recetario.domain.entities import ShoppingList


class ConnectGoogleTasks:
    def __init__(self, exporter: TaskExporter) -> None:
        self._exporter = exporter

    def __call__(self) -> None:
        self._exporter.connect()


class ExportShoppingListToTasks:
    def __init__(self, lists: ShoppingListRepository, exporter: TaskExporter) -> None:
        self._lists = lists
        self._exporter = exporter

    def __call__(self, list_id: int) -> ShoppingList:
        shopping_list = self._lists.get(list_id)
        if shopping_list is None:
            raise ShoppingListNotFoundError(list_id)
        if not self._exporter.is_connected():
            raise NotConnectedError("Google Tasks is not connected.")

        result = self._exporter.export(
            shopping_list, tasklist_id=shopping_list.external_tasklist_id
        )
        updated = self._lists.apply_export(
            list_id,
            tasklist_id=result.tasklist_id,
            item_task_ids=result.item_task_ids,
        )
        # apply_export only returns None if the row vanished mid-flight.
        return updated if updated is not None else shopping_list
