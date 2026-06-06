"""Settings endpoints: see which API keys are configured, and save your own.

This is the "bring your own keys" surface for the packaged app. Keys are written
to ~/.recetario/.env (0600) — the very file `Settings` reads on boot — and the
key-gated FDC / Anthropic factories are rebuilt on the spot, so a saved key takes
effect without restarting the app.

Security: the status response never returns a raw key, only whether it's set plus
a short masked hint. Secrets flow in, never out.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from recetario.api.factories import make_extractor_factory, make_provider_factory
from recetario.api.schemas import SecretStatus, SettingsStatusOut, SettingsUpdateIn
from recetario.infrastructure.config import Settings

router = APIRouter(prefix="/settings", tags=["settings"])

# API field -> the RECETARIO_ env var the store persists it under.
_ENV_VARS = {
    "fdc_api_key": "RECETARIO_FDC_API_KEY",
    "anthropic_api_key": "RECETARIO_ANTHROPIC_API_KEY",
    "anthropic_model": "RECETARIO_ANTHROPIC_MODEL",
}


def _mask(value: str | None) -> SecretStatus:
    if not value:
        return SecretStatus(configured=False, hint=None)
    tail = value[-4:] if len(value) >= 4 else value
    return SecretStatus(configured=True, hint=f"…{tail}")


def _effective(request: Request) -> Settings:
    """Settings scoped to the user config file the panel manages, so a freshly
    saved key is reflected immediately (and tests stay isolated to a tmp file)."""
    store = request.app.state.settings_store
    return Settings(_env_file=str(store.path))


def _status(settings: Settings) -> SettingsStatusOut:
    return SettingsStatusOut(
        fdc_api_key=_mask(settings.fdc_api_key),
        anthropic_api_key=_mask(settings.anthropic_api_key),
        anthropic_model=settings.anthropic_model,
    )


@router.get("", response_model=SettingsStatusOut)
def get_settings_status(request: Request) -> SettingsStatusOut:
    return _status(_effective(request))


@router.put("", response_model=SettingsStatusOut)
def update_settings(request: Request, body: SettingsUpdateIn) -> SettingsStatusOut:
    store = request.app.state.settings_store

    changes: dict[str, str | None] = {}
    for field in body.model_fields_set:  # only act on fields the client sent
        env_var = _ENV_VARS.get(field)
        if env_var is None:
            continue
        value = getattr(body, field)
        # The model has a built-in default and no meaningful "cleared" state.
        if field == "anthropic_model" and not value:
            continue
        changes[env_var] = value  # "" -> the store removes the key
    if changes:
        store.update(changes)

    # Rebuild the key-gated factories so a newly-saved key is usable right away,
    # without restarting the sidecar.
    settings = _effective(request)
    request.app.state.extractor_factory = make_extractor_factory(settings)
    request.app.state.nutrition_provider_factory = make_provider_factory(settings)
    return _status(settings)
