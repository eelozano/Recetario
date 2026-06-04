"""Google Tasks export adapter (implements the TaskExporter port).

Three layers, so the idempotent logic is testable without touching the network:

  * `GoogleTasksClient` — a tiny protocol of the two operations we need
    (find-or-create a task list; create-or-update a task).
  * `sync_list` — the **pure** idempotent orchestration: reuse the stored
    tasklist id and per-item task ids when present so re-export updates rather
    than duplicates. Unit-tested against a fake client.
  * `GoogleApiTasksClient` / `GoogleTasksConnector` — the real wiring: OAuth
    installed-app flow, encrypted token persistence, and the google-api client.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from recetario.application.ports.export import ExportResult, NotConnectedError, TaskExporter
from recetario.domain.entities import ShoppingList, ShoppingListItem

PROVIDER = "google_tasks"


# --- Pure, testable layer ----------------------------------------------------


class GoogleTasksClient(Protocol):
    def ensure_task_list(self, title: str, tasklist_id: str | None) -> str: ...

    def upsert_task(
        self, tasklist_id: str, *, task_id: str | None, title: str, completed: bool
    ) -> str: ...


def _fmt_qty(value: Decimal | None) -> str:
    if value is None:
        return ""
    # Trim trailing zeros: 4.000 -> "4", 0.500 -> "0.5".
    normalized = value.normalize()
    text = format(normalized, "f")
    return text


def task_title(item: ShoppingListItem) -> str:
    qty = _fmt_qty(item.total_quantity)
    amount = " ".join(p for p in [qty, (item.unit or "").strip()] if p)
    return f"{item.ingredient_name} — {amount}" if amount else item.ingredient_name


def sync_list(
    client: GoogleTasksClient, shopping_list: ShoppingList, tasklist_id: str | None
) -> ExportResult:
    """Idempotently push `shopping_list` to one task list, reusing ids when set."""
    resolved_list = client.ensure_task_list(shopping_list.name, tasklist_id)
    item_task_ids: dict[int, str] = {}
    for item in shopping_list.items:
        if item.id is None:
            continue
        task_id = client.upsert_task(
            resolved_list,
            task_id=item.external_task_id,
            title=task_title(item),
            completed=item.checked,
        )
        item_task_ids[item.id] = task_id
    return ExportResult(tasklist_id=resolved_list, item_task_ids=item_task_ids)


# --- Credential store protocol (structurally satisfied by the SQLAlchemy repo) -


class CredentialStore(Protocol):
    def get(self, provider: str): ...  # -> StoredCredential | None

    def save(
        self, provider: str, data: str, *, scopes: str | None = None, expires_at=None
    ) -> None: ...


# --- Real google-api client --------------------------------------------------


class GoogleApiTasksClient:
    """Wraps a built `tasks` v1 service. Network calls live only here."""

    def __init__(self, service) -> None:  # noqa: ANN001 - googleapiclient resource
        self._service = service

    def ensure_task_list(self, title: str, tasklist_id: str | None) -> str:
        from googleapiclient.errors import HttpError

        if tasklist_id:
            try:
                self._service.tasklists().patch(
                    tasklist=tasklist_id, body={"title": title}
                ).execute()
                return tasklist_id
            except HttpError as exc:
                if exc.resp.status != 404:
                    raise
                # Falls through to create a fresh list.
        created = self._service.tasklists().insert(body={"title": title}).execute()
        return created["id"]

    def upsert_task(
        self, tasklist_id: str, *, task_id: str | None, title: str, completed: bool
    ) -> str:
        from googleapiclient.errors import HttpError

        status = "completed" if completed else "needsAction"
        if task_id:
            try:
                self._service.tasks().patch(
                    tasklist=tasklist_id,
                    task=task_id,
                    body={"title": title, "status": status},
                ).execute()
                return task_id
            except HttpError as exc:
                if exc.resp.status != 404:
                    raise
                # Task was deleted upstream — recreate below.
        created = (
            self._service.tasks()
            .insert(tasklist=tasklist_id, body={"title": title, "status": status})
            .execute()
        )
        return created["id"]


# --- Connector (TaskExporter implementation) ---------------------------------


class GoogleTasksConnector(TaskExporter):
    def __init__(
        self,
        credentials: CredentialStore,
        *,
        client_secret_file: str,
        scopes: list[str],
        client_factory: Callable[[object], GoogleTasksClient] | None = None,
    ) -> None:
        self._credentials = credentials
        self._client_secret_file = client_secret_file
        self._scopes = scopes
        self._client_factory = client_factory or _build_api_client

    def is_connected(self) -> bool:
        return self._credentials.get(PROVIDER) is not None

    def connect(self) -> None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(self._client_secret_file, self._scopes)
        creds = flow.run_local_server(port=0)
        self._store(creds)

    def export(self, shopping_list: ShoppingList, *, tasklist_id: str | None) -> ExportResult:
        creds = self._load_credentials()
        client = self._client_factory(creds)
        return sync_list(client, shopping_list, tasklist_id)

    # -- internals ----------------------------------------------------------

    def _store(self, creds) -> None:  # noqa: ANN001 - google Credentials
        expires_at: datetime | None = getattr(creds, "expiry", None)
        self._credentials.save(
            PROVIDER,
            creds.to_json(),
            scopes=" ".join(self._scopes),
            expires_at=expires_at,
        )

    def _load_credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        stored = self._credentials.get(PROVIDER)
        if stored is None:
            raise NotConnectedError("Google Tasks is not connected.")
        creds = Credentials.from_authorized_user_info(json.loads(stored.data), self._scopes)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
            self._store(creds)
        return creds


def _build_api_client(creds) -> GoogleTasksClient:  # noqa: ANN001 - google Credentials
    from googleapiclient.discovery import build

    service = build("tasks", "v1", credentials=creds, cache_discovery=False)
    return GoogleApiTasksClient(service)
