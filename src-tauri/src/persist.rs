use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ShellRecord {
    pub id: String,
    pub name: String,
    pub cwd: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ProjectRecord {
    pub id: String,
    pub name: String,
    pub path: String,
    #[serde(default)]
    pub shells: Vec<ShellRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SessionState {
    #[serde(default)]
    pub projects: Vec<ProjectRecord>,
    #[serde(default)]
    pub active_project_id: Option<String>,
    #[serde(default)]
    pub active_shell_id: Option<String>,
    #[serde(default)]
    pub sidebar_width: Option<u32>,
}

pub fn config_file() -> PathBuf {
    let mut dir = dirs::config_dir().unwrap_or_else(std::env::temp_dir);
    dir.push("SideShell");
    let _ = std::fs::create_dir_all(&dir);
    dir.push("sessions.json");
    dir
}

pub fn load_state() -> SessionState {
    std::fs::read_to_string(config_file())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

pub fn save_state(state: &SessionState) -> anyhow::Result<()> {
    let path = config_file();
    let json = serde_json::to_string_pretty(state)?;
    std::fs::write(path, json)?;
    Ok(())
}
