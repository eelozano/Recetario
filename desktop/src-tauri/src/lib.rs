//! Tauri shell for Recetario.
//!
//! On startup we launch the bundled Python backend (`recetario-server`) as a
//! sidecar process. The React UI is "just another HTTP client" of that local
//! API (127.0.0.1:8765), so the whole app ships as one double-clickable bundle:
//! the sidecar self-migrates the user's SQLite DB and serves the API, the
//! webview renders the UI. The child is tracked in app state and killed on exit
//! so we never leak a backend process.

use std::sync::Mutex;

use tauri::{Listener, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the running sidecar so we can terminate it when the app exits.
struct Backend(Mutex<Option<CommandChild>>);

/// Label of the throwaway in-app browser used to import bot-protected pages.
const CAPTURE_LABEL: &str = "recipe-capture";

/// Read-only capture script injected into the import browser.
///
/// It adds a single floating "Import this recipe" button. On click it reads the
/// fully rendered `outerHTML` (the real browser has by then run any Cloudflare
/// JS challenge) and emits it back to the app as a `recipe-html-captured` event,
/// which the main window turns into a `from-html` ingestion job. The only thing
/// it writes to the page is its own button — it never touches the page's data,
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

/// Kill the sidecar if it's still tracked. Idempotent: `take()` means a second
/// call (e.g. ExitRequested then Exit) is a no-op.
fn kill_backend(app_handle: &tauri::AppHandle) {
    if let Some(child) = app_handle.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<CommandChild, Box<dyn std::error::Error>> {
    // Hand the sidecar our PID so it can self-terminate if we die without a
    // graceful exit (force-quit/crash). It watches this PID's liveness rather
    // than its own parent, because PyInstaller's bootloader sits between us and
    // the real Python process — see _resolve_watch_target in server.py.
    let (mut rx, child) = app
        .shell()
        .sidecar("recetario-server")?
        .env("RECETARIO_PARENT_PID", std::process::id().to_string())
        .spawn()?;

    // Drain the sidecar's stdout/stderr to the host console for debugging.
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    eprint!("[recetario-server] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(err) => {
                    eprintln!("[recetario-server] error: {err}");
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Backend(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![open_recipe_capture])
        .setup(|app| {
            let handle = app.handle().clone();
            match spawn_backend(&handle) {
                Ok(child) => {
                    *app.state::<Backend>().0.lock().unwrap() = Some(child);
                }
                Err(err) => {
                    eprintln!("Failed to start Recetario backend sidecar: {err}");
                }
            }

            // Close the import browser once it has handed back the page HTML.
            // The main window's React also receives this event (it's a global
            // emit) and turns it into a from-html ingestion job.
            let close_handle = app.handle().clone();
            app.listen_any("recipe-html-captured", move |_event| {
                if let Some(window) = close_handle.get_webview_window(CAPTURE_LABEL) {
                    let _ = window.close();
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Kill the sidecar on every graceful teardown path so no orphaned
            // backend keeps the port. ExitRequested fires when a quit is asked
            // for; Exit fires as the process actually unwinds (e.g. the last
            // window closing). We handle both — neither fires on a SIGKILL, which
            // is why the sidecar also self-terminates via a parent-death watchdog.
            match event {
                RunEvent::ExitRequested { .. } | RunEvent::Exit => kill_backend(app_handle),
                _ => {}
            }
        });
}
