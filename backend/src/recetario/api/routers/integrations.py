"""Integration endpoints: Google Tasks connection status + authorization.

`connect` runs the OAuth installed-app flow, which opens a browser on the host
machine and blocks until the user consents — fine for a local single-user app.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from recetario.api import deps
from recetario.api.schemas import IntegrationStatusOut
from recetario.application.ports import TaskExporter
from recetario.application.ports.export import ExportError
from recetario.application.use_cases.export import ConnectGoogleTasks

router = APIRouter(prefix="/integrations/google-tasks", tags=["integrations"])

_PROVIDER = "google_tasks"


def _client_configured(request: Request) -> bool:
    return Path(request.app.state.settings.google_client_secret_file).exists()


@router.get("", response_model=IntegrationStatusOut)
def google_tasks_status(
    request: Request,
    exporter: TaskExporter = Depends(deps.get_task_exporter),
):
    return IntegrationStatusOut(
        provider=_PROVIDER,
        connected=exporter.is_connected(),
        client_configured=_client_configured(request),
    )


@router.post("/connect", response_model=IntegrationStatusOut)
def google_tasks_connect(
    request: Request,
    uc: ConnectGoogleTasks = Depends(deps.connect_google_uc),
    exporter: TaskExporter = Depends(deps.get_task_exporter),
):
    if not _client_configured(request):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google OAuth client not configured. Place the downloaded "
                "client-secret JSON at the configured path first."
            ),
        )
    try:
        uc()
    except ExportError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - surface auth failures to the UI
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return IntegrationStatusOut(
        provider=_PROVIDER, connected=exporter.is_connected(), client_configured=True
    )
