use crate::shell_integration::prepare_shell_launch;
use anyhow::Result;
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use parking_lot::Mutex;
use portable_pty::{native_pty_system, ChildKiller, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::Arc;
use std::thread;
use tauri::{AppHandle, Emitter};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionInfo {
    pub id: String,
    pub project_id: String,
    pub cwd: String,
    pub rows: u16,
    pub cols: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PtyAttachSnapshot {
    pub data: String,
    pub last_seq: u64,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PtySpawnOptions {
    #[serde(default)]
    pub shell_executable: Option<String>,
    #[serde(default)]
    pub extra_env: HashMap<String, String>,
}

struct BufferedOutput {
    attached: bool,
    last_seq: u64,
    chunks: Vec<Vec<u8>>,
}

pub struct Session {
    pub info: Mutex<SessionInfo>,
    writer: Mutex<Box<dyn Write + Send>>,
    master: Mutex<Box<dyn MasterPty + Send>>,
    killer: Mutex<Box<dyn ChildKiller + Send + Sync>>,
    buffered_output: Mutex<BufferedOutput>,
}

impl Session {
    pub fn write_input(&self, data: &[u8]) -> std::io::Result<()> {
        let mut w = self.writer.lock();
        w.write_all(data)?;
        w.flush()
    }

    pub fn resize(&self, rows: u16, cols: u16) -> Result<()> {
        {
            let m = self.master.lock();
            m.resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })?;
        }
        let mut info = self.info.lock();
        info.rows = rows;
        info.cols = cols;
        Ok(())
    }

    pub fn kill(&self) {
        let mut k = self.killer.lock();
        let _ = k.kill();
    }

    pub fn record_output(&self, data: &[u8]) -> u64 {
        let mut buffered = self.buffered_output.lock();
        buffered.last_seq += 1;
        if !buffered.attached {
            buffered.chunks.push(data.to_vec());
        }
        buffered.last_seq
    }

    pub fn attach_output(&self) -> PtyAttachSnapshot {
        let mut buffered = self.buffered_output.lock();
        let total_len: usize = buffered.chunks.iter().map(Vec::len).sum();
        let mut joined = Vec::with_capacity(total_len);
        for chunk in buffered.chunks.drain(..) {
            joined.extend_from_slice(&chunk);
        }
        buffered.attached = true;

        PtyAttachSnapshot {
            data: B64.encode(joined),
            last_seq: buffered.last_seq,
        }
    }
}

pub struct PtyManager {
    sessions: Mutex<HashMap<String, Arc<Session>>>,
}

impl PtyManager {
    pub fn new() -> Self {
        Self {
            sessions: Mutex::new(HashMap::new()),
        }
    }

    pub fn get(&self, id: &str) -> Option<Arc<Session>> {
        self.sessions.lock().get(id).cloned()
    }

    pub fn insert(&self, id: String, session: Arc<Session>) {
        self.sessions.lock().insert(id, session);
    }

    pub fn remove(&self, id: &str) -> Option<Arc<Session>> {
        self.sessions.lock().remove(id)
    }

    pub fn list(&self) -> Vec<SessionInfo> {
        self.sessions
            .lock()
            .values()
            .map(|s| s.info.lock().clone())
            .collect()
    }

    pub fn kill_all(&self) {
        for s in self.sessions.lock().values() {
            s.kill();
        }
    }
}

pub fn spawn_session(
    app: AppHandle,
    manager: Arc<PtyManager>,
    project_id: String,
    cwd: String,
    rows: u16,
    cols: u16,
    options: PtySpawnOptions,
) -> Result<String> {
    let sys = native_pty_system();
    let pair = sys.openpty(PtySize {
        rows,
        cols,
        pixel_width: 0,
        pixel_height: 0,
    })?;

    let shell = resolve_shell(&options);
    let launch = prepare_shell_launch(&shell)?;
    let mut cmd = CommandBuilder::new(&launch.executable);
    for arg in &launch.args {
        cmd.arg(arg);
    }
    cmd.cwd(&cwd);
    for (k, v) in std::env::vars() {
        cmd.env(k, v);
    }
    for (k, v) in options.extra_env {
        cmd.env(k, v);
    }
    for (k, v) in launch.env {
        cmd.env(k, v);
    }
    cmd.env("TERM", "xterm-256color");
    cmd.env("COLORTERM", "truecolor");
    cmd.env("SIDESHELL", "1");
    cmd.env("SIDESHELL_SHELL_INTEGRATION", "1");

    let mut child = pair.slave.spawn_command(cmd)?;
    drop(pair.slave);

    let writer = pair.master.take_writer()?;
    let mut reader = pair.master.try_clone_reader()?;
    let killer = child.clone_killer();

    let id = Uuid::new_v4().to_string();

    let session = Arc::new(Session {
        info: Mutex::new(SessionInfo {
            id: id.clone(),
            project_id,
            cwd,
            rows,
            cols,
        }),
        writer: Mutex::new(writer),
        master: Mutex::new(pair.master),
        killer: Mutex::new(killer),
        buffered_output: Mutex::new(BufferedOutput {
            attached: false,
            last_seq: 0,
            chunks: Vec::new(),
        }),
    });

    manager.insert(id.clone(), session);

    // Reader thread — stream PTY output as base64 events
    {
        let app = app.clone();
        let id = id.clone();
        let session = manager.get(&id).expect("session inserted before reader");
        thread::spawn(move || {
            let mut buf = [0u8; 8192];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        let seq = session.record_output(&buf[..n]);
                        let data = B64.encode(&buf[..n]);
                        let _ = app.emit(
                            "pty://data",
                            serde_json::json!({ "sessionId": id, "data": data, "seq": seq }),
                        );
                    }
                    Err(_) => break,
                }
            }
        });
    }

    // Waiter thread — emit exit, clean up
    {
        let app = app.clone();
        let id = id.clone();
        let mgr = manager.clone();
        thread::spawn(move || {
            let status = child.wait();
            let code = status.map(|s| s.exit_code() as i32).unwrap_or(-1);
            mgr.remove(&id);
            let _ = app.emit(
                "pty://exit",
                serde_json::json!({ "sessionId": id, "code": code }),
            );
        });
    }

    Ok(id)
}

fn default_shell() -> String {
    #[cfg(target_os = "windows")]
    {
        if which_exe("pwsh.exe").is_some() {
            return "pwsh.exe".to_string();
        }
        "powershell.exe".to_string()
    }
    #[cfg(not(target_os = "windows"))]
    {
        std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string())
    }
}

fn resolve_shell(options: &PtySpawnOptions) -> String {
    options
        .shell_executable
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .unwrap_or_else(default_shell)
}

#[cfg(target_os = "windows")]
fn which_exe(name: &str) -> Option<std::path::PathBuf> {
    let path_var = std::env::var_os("PATH")?;
    for p in std::env::split_paths(&path_var) {
        let candidate = p.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}
