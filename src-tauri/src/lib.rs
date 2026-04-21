mod agent_restore;
mod commands;
mod persist;
mod pty;
mod shell_integration;

use pty::PtyManager;
use std::sync::Arc;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let manager = Arc::new(PtyManager::new());
    let kill_all_manager = manager.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(manager)
        .on_window_event(move |_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                kill_all_manager.kill_all();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::pty_spawn,
            commands::pty_write,
            commands::pty_resize,
            commands::pty_kill,
            commands::pty_list,
            commands::pty_attach,
            commands::load_state,
            commands::save_state,
            commands::path_exists,
            commands::resolve_agent_restore_target,
            commands::open_project_in_editor,
            commands::open_project_in_file_manager,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
