use crate::agent_restore::{
    resolve_agent_restore_target as resolve_agent_restore_target_impl, AgentRestoreResolveRequest,
    AgentRestoreResolveResult,
};
use crate::persist::{self, SessionState};
use crate::pty::{spawn_session, PtyAttachSnapshot, PtyManager, PtySpawnOptions, SessionInfo};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use std::path::Path;
use std::process::Command;
use std::sync::Arc;
use tauri::{AppHandle, State};

#[tauri::command]
pub fn pty_spawn(
    app: AppHandle,
    state: State<Arc<PtyManager>>,
    project_id: String,
    cwd: String,
    rows: u16,
    cols: u16,
    options: Option<PtySpawnOptions>,
) -> Result<String, String> {
    spawn_session(
        app,
        state.inner().clone(),
        project_id,
        cwd,
        rows,
        cols,
        options.unwrap_or_default(),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn pty_write(
    state: State<Arc<PtyManager>>,
    session_id: String,
    data: String,
) -> Result<(), String> {
    let bytes = B64.decode(data).map_err(|e| e.to_string())?;
    let session = state.get(&session_id).ok_or("session not found")?;
    session.write_input(&bytes).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn pty_resize(
    state: State<Arc<PtyManager>>,
    session_id: String,
    rows: u16,
    cols: u16,
) -> Result<(), String> {
    let session = state.get(&session_id).ok_or("session not found")?;
    session.resize(rows, cols).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn pty_kill(state: State<Arc<PtyManager>>, session_id: String) -> Result<(), String> {
    if let Some(s) = state.get(&session_id) {
        s.kill();
    }
    Ok(())
}

#[tauri::command]
pub fn pty_list(state: State<Arc<PtyManager>>) -> Vec<SessionInfo> {
    state.list()
}

#[tauri::command]
pub fn pty_attach(
    state: State<Arc<PtyManager>>,
    session_id: String,
) -> Result<PtyAttachSnapshot, String> {
    let session = state.get(&session_id).ok_or("session not found")?;
    Ok(session.attach_output())
}

#[tauri::command]
pub fn load_state() -> SessionState {
    persist::load_state()
}

#[tauri::command]
pub fn save_state(state: SessionState) -> Result<(), String> {
    persist::save_state(&state).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn path_exists(path: String) -> bool {
    std::path::Path::new(&path).exists()
}

#[tauri::command]
pub fn resolve_agent_restore_target(
    request: AgentRestoreResolveRequest,
) -> Result<Option<AgentRestoreResolveResult>, String> {
    resolve_agent_restore_target_impl(request)
}

fn validate_directory(path: &str) -> Result<&Path, String> {
    let project_path = Path::new(path);
    if !project_path.exists() {
        return Err(format!("path does not exist: {path}"));
    }
    if !project_path.is_dir() {
        return Err(format!("path is not a directory: {path}"));
    }
    Ok(project_path)
}

fn configure_external_command(command: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
}

fn spawn_external_command(
    command: &mut Command,
    executable_name: &str,
    missing_message: String,
    failure_context: &str,
) -> Result<(), String> {
    configure_external_command(command);
    command.spawn().map(|_| ()).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            return missing_message;
        }
        format!("failed to {failure_context} via {executable_name}: {error}")
    })
}

#[tauri::command]
pub fn open_project_in_editor(editor: String, path: String) -> Result<(), String> {
    validate_directory(&path)?;

    let (editor_command, not_found_message) = match editor.as_str() {
        "vscode" => (
            if cfg!(target_os = "windows") {
                "code.cmd"
            } else {
                "code"
            },
            "could not find `code` in PATH. Install VS Code and enable its shell command first."
                .to_string(),
        ),
        "zed" => (
            if cfg!(target_os = "windows") {
                "zed.exe"
            } else {
                "zed"
            },
            "could not find `zed` in PATH. Install Zed and enable its shell command first."
                .to_string(),
        ),
        _ => return Err(format!("unsupported editor: {editor}")),
    };

    let mut command = Command::new(editor_command);
    command.arg(&path);
    spawn_external_command(
        &mut command,
        editor_command,
        not_found_message,
        &format!("open project in {editor}"),
    )
}

#[tauri::command]
pub fn open_project_in_file_manager(path: String) -> Result<(), String> {
    validate_directory(&path)?;

    #[cfg(target_os = "windows")]
    let executable = "explorer.exe";
    #[cfg(target_os = "macos")]
    let executable = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let executable = "xdg-open";

    let mut command = Command::new(executable);
    command.arg(&path);
    spawn_external_command(
        &mut command,
        executable,
        format!("could not find `{executable}` in PATH."),
        "open project folder",
    )
}
