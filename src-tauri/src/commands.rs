use crate::persist::{self, SessionState};
use crate::pty::{spawn_session, PtyAttachSnapshot, PtyManager, SessionInfo};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
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
) -> Result<String, String> {
    spawn_session(app, state.inner().clone(), project_id, cwd, rows, cols)
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
