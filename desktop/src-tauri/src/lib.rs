//! Tauri shell for Recetario.
//!
//! On startup we launch the bundled Python backend (`recetario-server`) as a
//! sidecar process. The React UI is "just another HTTP client" of that local
//! API (127.0.0.1:8765), so the whole app ships as one double-clickable bundle:
//! the sidecar self-migrates the user's SQLite DB and serves the API, the
//! webview renders the UI. The child is tracked in app state and killed on exit
//! so we never leak a backend process.

use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the running sidecar so we can terminate it when the app exits.
struct Backend(Mutex<Option<CommandChild>>);

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
