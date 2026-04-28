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

    let mut builder = tauri::Builder::default();

    #[cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }

            for arg in _argv {
                if let Some(tag) = shell_alert_tag_from_deep_link(&arg) {
                    desktop_notifications::emit_shell_notification_activated(app, tag);
                }
            }
        }));
    }

    builder
        .plugin(tauri_plugin_deep_link::init())
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

fn shell_alert_tag_from_deep_link(value: &str) -> Option<String> {
    let trimmed = value.trim();
    let query = trimmed.strip_prefix("sideshell://shell-alert?")?;
    for pair in query.split('&') {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        if key != "tag" {
            continue;
        }

        let tag = percent_decode_query_value(value)?;
        if tag.starts_with("sideshell-shell-") {
            return Some(tag);
        }
    }
    None
}

fn percent_decode_query_value(value: &str) -> Option<String> {
    let mut bytes = Vec::with_capacity(value.len());
    let mut chars = value.as_bytes().iter().copied();
    while let Some(byte) = chars.next() {
        match byte {
            b'+' => bytes.push(b' '),
            b'%' => {
                let high = chars.next()?;
                let low = chars.next()?;
                bytes.push((hex_value(high)? << 4) | hex_value(low)?);
            }
            _ => bytes.push(byte),
        }
    }
    String::from_utf8(bytes).ok()
}

fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}
