use once_cell::sync::Lazy;
use parking_lot::Mutex;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

static LOG_FILE: Lazy<Mutex<Option<File>>> = Lazy::new(|| Mutex::new(open_log_file()));

pub fn info(target: &str, message: impl AsRef<str>) {
    write_line("INFO", target, message.as_ref());
}

pub fn warn(target: &str, message: impl AsRef<str>) {
    write_line("WARN", target, message.as_ref());
}

pub fn error(target: &str, message: impl AsRef<str>) {
    write_line("ERROR", target, message.as_ref());
}

pub fn log_file_path() -> Option<PathBuf> {
    log_dir().map(|dir| dir.join("runtime.log"))
}

fn write_line(level: &str, target: &str, message: &str) {
    let timestamp_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    let line = format!("[{timestamp_ms}] {level:<5} {target}: {message}\n");

    let mut file = LOG_FILE.lock();
    if file.is_none() {
        *file = open_log_file();
    }
    if let Some(file) = file.as_mut() {
        let _ = file.write_all(line.as_bytes());
        let _ = file.flush();
    }

    #[cfg(debug_assertions)]
    eprint!("{line}");
}

fn open_log_file() -> Option<File> {
    let path = log_file_path()?;
    let parent = path.parent()?;
    if std::fs::create_dir_all(parent).is_err() {
        return None;
    }

    OpenOptions::new().create(true).append(true).open(path).ok()
}

fn log_dir() -> Option<PathBuf> {
    let mut path = dirs::config_dir().unwrap_or_else(std::env::temp_dir);
    path.push("SideShell");
    path.push("logs");
    Some(path)
}
