use crate::runtime_log;
use crate::shell_integration::prepare_shell_launch;
use anyhow::Result;
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use parking_lot::Mutex;
use portable_pty::{native_pty_system, ChildKiller, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::io::{Read, Write};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter};
use uuid::Uuid;

const MAX_BUFFERED_OUTPUT_BYTES: usize = 512 * 1024; // 512KB is plenty for scrollback
const PTY_READ_BUFFER_BYTES: usize = 16 * 1024;
const PTY_EMIT_BATCH_BYTES: usize = 128 * 1024;
const PTY_EMIT_BATCH_WINDOW: Duration = Duration::from_millis(8);

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
    total_bytes: usize,
    chunks: VecDeque<Vec<u8>>,
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
        if let Err(error) = k.kill() {
            runtime_log::warn("pty", format!("kill failed error={error}"));
        }
    }

    pub fn record_output(&self, data: &[u8]) -> u64 {
        let mut buffered = self.buffered_output.lock();
        buffered.last_seq += 1;
        push_buffered_chunk(&mut buffered, data);
        buffered.last_seq
    }

    pub fn attach_output(&self) -> PtyAttachSnapshot {
        let mut buffered = self.buffered_output.lock();
        let mut joined = Vec::with_capacity(buffered.total_bytes);
        for chunk in &buffered.chunks {
            joined.extend_from_slice(chunk);
        }
        buffered.attached = true;

        PtyAttachSnapshot {
            data: B64.encode(joined),
            last_seq: buffered.last_seq,
        }
    }
}

fn push_buffered_chunk(buffered: &mut BufferedOutput, data: &[u8]) {
    if data.is_empty() {
        return;
    }

    buffered.total_bytes += data.len();
    buffered.chunks.push_back(data.to_vec());

    while buffered.total_bytes > MAX_BUFFERED_OUTPUT_BYTES {
        let Some(removed) = buffered.chunks.pop_front() else {
            buffered.total_bytes = 0;
            break;
        };
        buffered.total_bytes = buffered.total_bytes.saturating_sub(removed.len());
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
        let sessions = self.sessions.lock();
        runtime_log::info("pty", format!("kill_all count={}", sessions.len()));
        for s in sessions.values() {
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
    runtime_log::info(
        "pty",
        format!(
            "spawn requested project_id={} rows={} cols={} cwd={}",
            project_id, rows, cols, cwd
        ),
    );

    let sys = native_pty_system();
    let pair = match sys.openpty(PtySize {
        rows,
        cols,
        pixel_width: 0,
        pixel_height: 0,
    }) {
        Ok(pair) => pair,
        Err(error) => {
            runtime_log::error("pty", format!("openpty failed error={error}"));
            return Err(error.into());
        }
    };

    let shell = resolve_shell(&options);
    let launch = match prepare_shell_launch(&shell) {
        Ok(launch) => launch,
        Err(error) => {
            runtime_log::error(
                "pty",
                format!("prepare shell launch failed shell={shell} error={error}"),
            );
            return Err(error);
        }
    };
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

    let mut child = match pair.slave.spawn_command(cmd) {
        Ok(child) => child,
        Err(error) => {
            runtime_log::error(
                "pty",
                format!(
                    "spawn command failed executable={} shell={} error={error}",
                    launch.executable, shell
                ),
            );
            return Err(error.into());
        }
    };
    drop(pair.slave);

    let writer = match pair.master.take_writer() {
        Ok(writer) => writer,
        Err(error) => {
            runtime_log::error("pty", format!("take writer failed error={error}"));
            return Err(error.into());
        }
    };
    let mut reader = match pair.master.try_clone_reader() {
        Ok(reader) => reader,
        Err(error) => {
            runtime_log::error("pty", format!("clone reader failed error={error}"));
            return Err(error.into());
        }
    };
    let killer = child.clone_killer();

    let id = Uuid::new_v4().to_string();

    let session = Arc::new(Session {
        info: Mutex::new(SessionInfo {
            id: id.clone(),
            project_id: project_id.clone(),
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
            total_bytes: 0,
            chunks: VecDeque::new(),
        }),
    });

    manager.insert(id.clone(), session);
    runtime_log::info(
        "pty",
        format!(
            "spawned session_id={} project_id={} executable={} shell={}",
            id, project_id, launch.executable, shell
        ),
    );

    // Reader thread — batch PTY output before emitting IPC events.
    {
        let app = app.clone();
        let id = id.clone();
        let reader_id = id.clone();
        let session = manager.get(&id).expect("session inserted before reader");
        let (output_tx, mut output_rx) = tokio::sync::mpsc::channel::<Vec<u8>>(32);

        tokio::task::spawn_blocking(move || {
            let mut buf = [0u8; PTY_READ_BUFFER_BYTES];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        if output_tx.blocking_send(buf[..n].to_vec()).is_err() {
                            runtime_log::warn(
                                "pty",
                                format!("reader channel closed session_id={reader_id}"),
                            );
                            break;
                        }
                    }
                    Err(error) => {
                        runtime_log::warn(
                            "pty",
                            format!("reader failed session_id={reader_id} error={error}"),
                        );
                        break;
                    }
                }
            }
            runtime_log::info("pty", format!("reader stopped session_id={reader_id}"));
        });

        tokio::spawn(async move {
            while let Some(first_chunk) = output_rx.recv().await {
                let mut batch = first_chunk;
                let deadline = tokio::time::Instant::now() + PTY_EMIT_BATCH_WINDOW;

                while batch.len() < PTY_EMIT_BATCH_BYTES {
                    match tokio::time::timeout_at(deadline, output_rx.recv()).await {
                        Ok(Some(chunk)) => batch.extend_from_slice(&chunk),
                        Ok(None) => break,
                        Err(_) => break,
                    }
                }

                let seq = session.record_output(&batch);
                let data = B64.encode(&batch);
                if let Err(error) = app.emit(
                    "pty://data",
                    serde_json::json!({ "sessionId": id, "data": data, "seq": seq }),
                ) {
                    runtime_log::warn(
                        "pty",
                        format!("emit data failed session_id={id} seq={seq} error={error}"),
                    );
                }
            }
            runtime_log::info("pty", format!("emitter stopped session_id={id}"));
        });
    }

    // Waiter task — emit exit, clean up asynchronously
    {
        let app = app.clone();
        let id = id.clone();
        let mgr = manager.clone();
        tokio::spawn(async move {
            let code = loop {
                match child.try_wait() {
                    Ok(Some(status)) => break status.exit_code() as i32,
                    Ok(None) => {
                        tokio::time::sleep(Duration::from_millis(100)).await;
                    }
                    Err(error) => {
                        runtime_log::warn(
                            "pty",
                            format!("wait failed session_id={id} error={error}"),
                        );
                        break -1;
                    }
                }
            };
            mgr.remove(&id);
            runtime_log::info("pty", format!("session exited session_id={id} code={code}"));
            if let Err(error) = app.emit(
                "pty://exit",
                serde_json::json!({ "sessionId": id, "code": code }),
            ) {
                runtime_log::warn(
                    "pty",
                    format!("emit exit failed session_id={id} code={code} error={error}"),
                );
            }
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
