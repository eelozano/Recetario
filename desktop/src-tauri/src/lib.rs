//! Tauri shell for Recetario.
//!
//! Architecture v2: the app is a local-first desktop client. The React UI reads
//! and writes recipes, the meal calendar, and shopping lists as flat files under
//! the user's Documents folder via the `fs` plugin (scoped by
//! `capabilities/default.json`). There is no backend server.
//!
//! Recipe **import** is the one exception to "pure files": it shells out to the
//! `recetario-helper` sidecar (a frozen Python CLI) for URL/video/from-HTML
//! extraction, which prints a JSON draft the React side turns into a recipe file.
//! That sidecar is spawned on demand via the `shell` plugin — it is not a
//! long-running process. The `open_recipe_capture` command below opens an in-app
//! browser for the from-HTML path (bot-protected pages a server-side fetch can't
//! reach); an injected button hands the rendered HTML back to the app.

use tauri::{Listener, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_fs::FsExt;

mod config;

/// Label of the throwaway in-app browser used to import bot-protected pages.
const CAPTURE_LABEL: &str = "recipe-capture";

/// Read-only capture script injected into the import browser.
///
/// It adds a single floating "Import this recipe" button. On click it reads the
/// fully rendered `outerHTML` (the real browser has by then run any Cloudflare
/// JS challenge) and emits it back to the app as a `recipe-html-captured` event,
/// which the main window turns into a from-html import job. The only thing it
/// writes to the page is its own button — it never touches the page's data,
/// forms, or credentials. Capabilities limit this webview to emitting events and
/// nothing else (no fs/shell/window access).
const CAPTURE_JS: &str = r#"
;(function () {
  if (window.top !== window.self) return; // main frame only
  var BTN_ID = 'recetario-capture-btn';
  function capture() {
    try {
      window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {
        event: 'recipe-html-captured',
        payload: { url: window.location.href, html: document.documentElement.outerHTML }
      });
      var b = document.getElementById(BTN_ID);
      if (b) { b.textContent = 'Imported ✓'; b.disabled = true; }
    } catch (e) { /* swallow: nothing we can surface from here */ }
  }
  function inject() {
    if (!document.body || document.getElementById(BTN_ID)) return;
    var btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.type = 'button';
    btn.textContent = 'Import this recipe';
    btn.style.cssText =
      'position:fixed;right:16px;bottom:16px;z-index:2147483647;' +
      'background:#b4532a;color:#fff;border:none;border-radius:10px;' +
      'padding:12px 18px;font:600 14px system-ui,-apple-system,sans-serif;' +
      'box-shadow:0 4px 16px rgba(0,0,0,.35);cursor:pointer;';
    btn.addEventListener('click', capture);
    document.body.appendChild(btn);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
"#;

/// Open an in-app browser at `url` to import a recipe a server-side fetch can't
/// reach (e.g. Cloudflare-protected pages). The window renders the page as a real
/// browser; an injected button captures the rendered HTML back to the app.
#[tauri::command]
fn open_recipe_capture(app: tauri::AppHandle, url: String) -> Result<(), String> {
    let parsed = tauri::Url::parse(url.trim()).map_err(|e| format!("Invalid URL: {e}"))?;
    // One capture window at a time — replace any stale one.
    if let Some(existing) = app.get_webview_window(CAPTURE_LABEL) {
        let _ = existing.close();
    }
    WebviewWindowBuilder::new(&app, CAPTURE_LABEL, WebviewUrl::External(parsed))
        .title("Import a recipe — load the page, then click “Import this recipe”")
        .inner_size(1024.0, 800.0)
        .initialization_script(CAPTURE_JS)
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Extend the fs plugin's runtime scope to a directory (and its subtree) so the
/// frontend can read/write a data dir outside the static capability scope. The
/// plugin allows a path when EITHER the capability scope or this runtime scope
/// permits it (tauri-plugin-fs `resolve_path`), so this is how a user-picked
/// folder becomes usable.
fn allow_data_dir(app: &tauri::AppHandle, dir: &str) -> Result<(), String> {
    app.fs_scope()
        .allow_directory(dir, true)
        .map_err(|e| format!("Could not grant access to {dir}: {e}"))
}

/// The active data dir (configured override or the default), as an absolute path.
#[tauri::command]
fn get_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    Ok(config::effective_data_dir(&app)?.to_string_lossy().into_owned())
}

/// The default data dir, regardless of any override. Settings compares it against
/// the active dir to decide whether a "Reset to default" control is meaningful.
#[tauri::command]
fn get_default_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    Ok(config::default_data_dir(&app)?.to_string_lossy().into_owned())
}

/// Point the app at a new data dir: unlock it in the fs scope and persist it.
/// Returns the stored path. The caller reloads so the repositories rebuild.
#[tauri::command]
fn set_data_dir(app: tauri::AppHandle, path: String) -> Result<String, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("Please choose a folder.".into());
    }
    allow_data_dir(&app, trimmed)?;
    let mut cfg = config::load(&app);
    cfg.data_dir = Some(trimmed.to_string());
    config::save(&app, &cfg)?;
    Ok(trimmed.to_string())
}

/// Clear the override so the app falls back to the default data dir. Returns the
/// default path. The caller reloads so the repositories rebuild.
#[tauri::command]
fn reset_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    let mut cfg = config::load(&app);
    cfg.data_dir = None;
    config::save(&app, &cfg)?;
    Ok(config::default_data_dir(&app)?.to_string_lossy().into_owned())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        // Flat-file data store (Architecture v2, step 3): the React data layer
        // reads/writes recipes, calendar, and shopping files through this plugin,
        // scoped to the data dir by capabilities/default.json.
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            open_recipe_capture,
            get_data_dir,
            get_default_data_dir,
            set_data_dir,
            reset_data_dir
        ])
        .setup(|app| {
            // A custom data dir (step 5) lives outside the static fs scope, so
            // unlock it before the webview loads and touches the filesystem.
            if let Some(dir) = config::load(app.handle()).data_dir {
                if !dir.trim().is_empty() {
                    if let Err(e) = allow_data_dir(app.handle(), &dir) {
                        eprintln!("[recetario] {e}");
                    }
                }
            }
            // Close the import browser once it has handed back the page HTML.
            // The main window's React also receives this event (it's a global
            // emit) and turns it into a from-html import job.
            let close_handle = app.handle().clone();
            app.listen_any("recipe-html-captured", move |_event| {
                if let Some(window) = close_handle.get_webview_window(CAPTURE_LABEL) {
                    let _ = window.close();
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
