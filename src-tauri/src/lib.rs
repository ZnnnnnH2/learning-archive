mod commands;
mod desktop_notifications;
mod persist;
mod pty;
mod shell_integration;

use desktop_notifications::DesktopNotificationService;
use pty::PtyManager;
use std::sync::Arc;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let manager = Arc::new(PtyManager::new());
    let kill_all_manager = manager.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(manager)
        .setup(|app| {
            app.manage(DesktopNotificationService::new(app.handle().clone()));
            Ok(())
        })
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
            commands::send_shell_notification,
            commands::close_shell_notification,
            commands::open_project_in_editor,
            commands::open_project_in_file_manager,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
