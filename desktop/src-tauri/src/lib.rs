//! Tauri shell for Recetario.
//!
//! Architecture v2: the app is a pure local-first desktop client. The React UI
//! reads and writes recipes, the meal calendar, and shopping lists as flat files
//! under the user's Documents folder via the `fs` plugin (scoped by
//! `capabilities/default.json`). There is no backend process and no localhost
//! API — the former Python sidecar was removed in step 3. Recipe ingestion will
//! return as a separate, on-demand helper in a later step.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        // Flat-file data store (Architecture v2, step 3): the React data layer
        // reads/writes recipes, calendar, and shopping files through this plugin,
        // scoped to the data dir by capabilities/default.json.
        .plugin(tauri_plugin_fs::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
