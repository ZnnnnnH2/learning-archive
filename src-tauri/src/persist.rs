use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct RestoreTargetRecord {
    pub kind: String,
    pub value: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ShellRecord {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<i64>,
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub auto_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name_mode: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_label: Option<String>,
    #[serde(default)]
    pub resume_entry_command: Option<String>,
    #[serde(default)]
    pub new_session_command: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_capability: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_command_prefix: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_command_suffix: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_fallback_command: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_target: Option<RestoreTargetRecord>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_resolve_pending: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_resolve_strategy: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_launch_started_at: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore_launch_cwd: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resume_command: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub first_message_preview: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_summary: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub terminal_title: Option<String>,
    pub cwd: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ProjectRecord {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<i64>,
    pub name: String,
    pub path: String,
    #[serde(default)]
    pub shells: Vec<ShellRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct TerminalSettingsRecord {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub locale: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shell_executable: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub font_family: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub extra_env_text: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub alert_popup_duration_seconds: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub codex_use_self_summary_title: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shortcut_keymap: Option<serde_json::Value>,
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
    #[serde(default)]
    pub terminal: TerminalSettingsRecord,
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
