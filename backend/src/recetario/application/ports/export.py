"""Task-export port — the boundary for pushing a shopping list to an external
task service (Google Tasks now; Todoist/Reminders later behind the same port)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from recetario.domain.entities import ShoppingList


class ExportError(Exception):
    """Raised when an export fails (network, API, etc.)."""


class NotConnectedError(ExportError):
    """Raised when an export is attempted before the integration is authorized."""


@dataclass
class ExportResult:
    """Outcome of a sync: the external task-list id plus a mapping from each
    shopping-list item id to its external task id (used for idempotent re-sync)."""

    tasklist_id: str
    item_task_ids: dict[int, str]


class TaskExporter(Protocol):
    def is_connected(self) -> bool: ...

    def connect(self) -> None:
        """Run the (interactive) authorization flow and persist credentials."""
        ...

    def export(
        self, shopping_list: ShoppingList, *, tasklist_id: str | None
    ) -> ExportResult: ...
