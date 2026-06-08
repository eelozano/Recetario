//! App configuration (Architecture v2, step 5).
//!
//! A tiny JSON file at `~/.recetario/config.json` records the user's chosen data
//! directory. It lives OUTSIDE the synced data dir (and outside the fs plugin's
//! capability scope), so it's read/written here on the Rust side with `std::fs`
//! rather than through the fs plugin. The only field today is the data dir; the
//! default (when unset) is `<documents>/Recetario/data`, which already sits inside
//! the static fs scope. A custom dir is unlocked at runtime via `allow_directory`
//! (see lib.rs).

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, Runtime};

/// Persisted app config. `data_dir = None` means "use the default".
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct AppConfig {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data_dir: Option<String>,
}

/// `~/.recetario` — holds config.json (and, separately, the helper's .env/secrets).
fn config_dir<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    let home = app
        .path()
        .home_dir()
        .map_err(|e| format!("Could not resolve the home directory: {e}"))?;
    Ok(home.join(".recetario"))
}

/// `~/.recetario/config.json`.
pub fn config_path<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    Ok(config_dir(app)?.join("config.json"))
}

/// Read the config; a missing or unparseable file yields defaults (never panics).
pub fn load<R: Runtime>(app: &AppHandle<R>) -> AppConfig {
    let Ok(path) = config_path(app) else {
        return AppConfig::default();
    };
    match std::fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
        Err(_) => AppConfig::default(),
    }
}

/// Persist the config, creating `~/.recetario` if needed.
pub fn save<R: Runtime>(app: &AppHandle<R>, config: &AppConfig) -> Result<(), String> {
    let dir = config_dir(app)?;
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("Could not create {}: {e}", dir.display()))?;
    let path = dir.join("config.json");
    let text = serde_json::to_string_pretty(config)
        .map_err(|e| format!("Could not serialize config: {e}"))?;
    std::fs::write(&path, text)
        .map_err(|e| format!("Could not write {}: {e}", path.display()))?;
    Ok(())
}

/// `<documents>/Recetario/data` — the default store, inside the static fs scope.
pub fn default_data_dir<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    let docs = app
        .path()
        .document_dir()
        .map_err(|e| format!("Could not resolve the Documents directory: {e}"))?;
    Ok(docs.join("Recetario").join("data"))
}

/// The active data dir: the configured override, else the default.
pub fn effective_data_dir<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    match load(app).data_dir {
        Some(dir) if !dir.trim().is_empty() => Ok(PathBuf::from(dir)),
        _ => default_data_dir(app),
    }
}
