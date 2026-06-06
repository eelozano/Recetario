import { type FormEvent, useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { api, type SettingsStatus, type SettingsUpdate } from "../api/client";

// Where to get each key. FDC is free + instant; Anthropic is paid + optional.
const FDC_SIGNUP = "https://fdc.nal.usda.gov/api-key-signup.html";
const ANTHROPIC_KEYS = "https://console.anthropic.com/settings/keys";

/**
 * Bring-your-own-keys panel. The app works without keys (recipes, macros,
 * calendar, shopping); these unlock the two live features:
 *   • USDA FoodData Central key → live ingredient search + on-the-fly linking
 *   • Anthropic key            → LLM-assisted recipe import from a URL
 *
 * Keys are written to ~/.recetario/.env on this machine and never leave it. The
 * status we load back only says whether each key is set (plus a masked hint) —
 * the raw values are never sent to the UI.
 */
export function Settings() {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fdcInput, setFdcInput] = useState("");
  const [anthropicInput, setAnthropicInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    setLoading(true);
    const { data, error: apiError } = await api.GET("/settings");
    if (apiError) setError("Could not load settings.");
    else {
      setStatus(data ?? null);
      setError(null);
    }
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  async function persist(update: SettingsUpdate) {
    setSaving(true);
    setSaved(false);
    const { data, error: apiError } = await api.PUT("/settings", { body: update });
    if (apiError || !data) {
      setError("Could not save settings.");
    } else {
      setStatus(data);
      setError(null);
      setFdcInput("");
      setAnthropicInput("");
      setSaved(true);
    }
    setSaving(false);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    // Only send fields the user actually typed into — an untouched field is
    // left exactly as it was on the server.
    const update: SettingsUpdate = {};
    if (fdcInput.trim()) update.fdc_api_key = fdcInput.trim();
    if (anthropicInput.trim()) update.anthropic_api_key = anthropicInput.trim();
    if (Object.keys(update).length === 0) return;
    await persist(update);
  }

  if (loading) return <p className="muted">Loading settings…</p>;

  return (
    <div className="settings">
      <h2>Settings</h2>
      <p className="muted settings__intro">
        Recetario works out of the box. Add your own API keys to unlock live USDA
        nutrition lookups and AI-assisted recipe import. Keys are stored only on
        this computer (<code>~/.recetario/.env</code>) and take effect immediately.
      </p>

      {error && <p className="error">{error}</p>}
      {saved && !error && <p className="settings__saved">Saved — your changes are live.</p>}

      <form className="settings__form" onSubmit={onSubmit}>
        <KeyField
          label="USDA FoodData Central key"
          help="Free and instant. Enables live ingredient search and macro linking."
          status={status?.fdc_api_key}
          value={fdcInput}
          onChange={setFdcInput}
          getKeyUrl={FDC_SIGNUP}
          getKeyLabel="Get a free FDC key"
          onClear={
            status?.fdc_api_key.configured
              ? () => void persist({ fdc_api_key: "" })
              : undefined
          }
          disabled={saving}
        />

        <KeyField
          label="Anthropic API key"
          help="Paid. Enables importing a recipe from a web or video URL via Claude."
          status={status?.anthropic_api_key}
          value={anthropicInput}
          onChange={setAnthropicInput}
          getKeyUrl={ANTHROPIC_KEYS}
          getKeyLabel="Get an Anthropic key"
          onClear={
            status?.anthropic_api_key.configured
              ? () => void persist({ anthropic_api_key: "" })
              : undefined
          }
          disabled={saving}
        />

        <div className="settings__actions">
          <button
            type="submit"
            className="btn btn--accent"
            disabled={saving || (!fdcInput.trim() && !anthropicInput.trim())}
          >
            {saving ? "Saving…" : "Save keys"}
          </button>
        </div>
      </form>
    </div>
  );
}

function KeyField({
  label,
  help,
  status,
  value,
  onChange,
  getKeyUrl,
  getKeyLabel,
  onClear,
  disabled,
}: {
  label: string;
  help: string;
  status?: { configured: boolean; hint?: string | null };
  value: string;
  onChange: (v: string) => void;
  getKeyUrl: string;
  getKeyLabel: string;
  onClear?: () => void;
  disabled: boolean;
}) {
  const configured = status?.configured ?? false;
  return (
    <div className="settings__field">
      <div className="settings__field-head">
        <label className="settings__label">{label}</label>
        {configured ? (
          <span className="settings__badge settings__badge--ok">
            Configured{status?.hint ? ` · ${status.hint}` : ""}
          </span>
        ) : (
          <span className="settings__badge">Not set</span>
        )}
      </div>
      <p className="muted settings__help">{help}</p>
      <div className="settings__input-row">
        <input
          type="password"
          className="settings__input"
          placeholder={configured ? "Enter a new key to replace" : "Paste your key"}
          value={value}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
        {onClear && (
          <button
            type="button"
            className="link-btn link-btn--danger"
            onClick={onClear}
            disabled={disabled}
          >
            Clear
          </button>
        )}
      </div>
      <button
        type="button"
        className="settings__link"
        onClick={() => void openUrl(getKeyUrl)}
      >
        {getKeyLabel} ↗
      </button>
    </div>
  );
}
