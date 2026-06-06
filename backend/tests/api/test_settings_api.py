"""Settings (BYO API keys) endpoint tests — all offline.

Every test points the app's settings store at a throwaway tmp file so the real
~/.recetario/.env is never read or written, and clears any RECETARIO_* key vars
from the environment so the effective status is determined solely by that file.
"""

import pytest

from recetario.infrastructure.settings_store import EnvFileSettingsStore


@pytest.fixture
def store_path(tmp_path, client, monkeypatch):
    """Isolate the Settings store to a tmp .env and a clean environment."""
    monkeypatch.delenv("RECETARIO_FDC_API_KEY", raising=False)
    monkeypatch.delenv("RECETARIO_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("RECETARIO_ANTHROPIC_MODEL", raising=False)
    path = tmp_path / ".env"
    client.app.state.settings_store = EnvFileSettingsStore(path)
    return path


def test_status_defaults_to_unconfigured(client, store_path):
    body = client.get("/settings").json()
    assert body["fdc_api_key"] == {"configured": False, "hint": None}
    assert body["anthropic_api_key"] == {"configured": False, "hint": None}
    # The model has a built-in default even with no file.
    assert body["anthropic_model"]


def test_put_saves_keys_and_masks_them(client, store_path):
    resp = client.put(
        "/settings",
        json={"fdc_api_key": "FDCKEY1234", "anthropic_api_key": "sk-ant-secretZ9"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fdc_api_key"] == {"configured": True, "hint": "…1234"}
    assert body["anthropic_api_key"] == {"configured": True, "hint": "…etZ9"}

    # The raw secrets must never appear in the response.
    assert "FDCKEY1234" not in resp.text
    assert "sk-ant-secretZ9" not in resp.text

    # Persisted to the tmp file under the RECETARIO_ prefix.
    saved = EnvFileSettingsStore(store_path).read()
    assert saved["RECETARIO_FDC_API_KEY"] == "FDCKEY1234"
    assert saved["RECETARIO_ANTHROPIC_API_KEY"] == "sk-ant-secretZ9"

    # Survives a re-read via GET.
    assert client.get("/settings").json()["fdc_api_key"]["configured"] is True


def test_saving_keys_enables_live_factories_without_restart(client, store_path):
    # Before: no keys, so the key-gated factories yield nothing.
    assert client.app.state.nutrition_provider_factory() is None
    assert client.app.state.extractor_factory() is None

    client.put(
        "/settings",
        json={"fdc_api_key": "FDCKEY1234", "anthropic_api_key": "sk-ant-secretZ9"},
    )

    # After: the same app.state factories now build live adapters — the change
    # took effect immediately, no sidecar restart.
    assert client.app.state.nutrition_provider_factory() is not None
    assert client.app.state.extractor_factory() is not None


def test_empty_string_clears_a_key(client, store_path):
    client.put("/settings", json={"fdc_api_key": "FDCKEY1234"})
    assert client.app.state.nutrition_provider_factory() is not None

    cleared = client.put("/settings", json={"fdc_api_key": ""})
    assert cleared.json()["fdc_api_key"] == {"configured": False, "hint": None}
    assert client.app.state.nutrition_provider_factory() is None
    assert "RECETARIO_FDC_API_KEY" not in EnvFileSettingsStore(store_path).read()


def test_omitted_field_is_left_unchanged(client, store_path):
    client.put("/settings", json={"fdc_api_key": "FDCKEY1234"})
    # Update only the Anthropic key; FDC must be untouched.
    body = client.put("/settings", json={"anthropic_api_key": "sk-ant-secretZ9"}).json()
    assert body["fdc_api_key"]["configured"] is True
    assert body["anthropic_api_key"]["configured"] is True


def test_update_preserves_unmanaged_lines(client, store_path):
    store_path.write_text(
        "# my recetario config\nRECETARIO_DATABASE_URL=sqlite:////tmp/x.db\n"
    )
    client.put("/settings", json={"fdc_api_key": "FDCKEY1234"})

    text = store_path.read_text()
    assert "# my recetario config" in text
    assert "RECETARIO_DATABASE_URL=sqlite:////tmp/x.db" in text
    assert "RECETARIO_FDC_API_KEY=FDCKEY1234" in text


def test_can_set_anthropic_model_but_empty_is_ignored(client, store_path):
    body = client.put("/settings", json={"anthropic_model": "claude-test-9"}).json()
    assert body["anthropic_model"] == "claude-test-9"
    # An empty model is ignored (it has a non-null default, no "cleared" state).
    body2 = client.put("/settings", json={"anthropic_model": ""}).json()
    assert body2["anthropic_model"] == "claude-test-9"
