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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        // Flat-file data store (Architecture v2, step 3): the React data layer
        // reads/writes recipes, calendar, and shopping files through this plugin,
        // scoped to the data dir by capabilities/default.json.
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![open_recipe_capture])
        .setup(|app| {
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
