use rusqlite::{Connection, OpenFlags, Row};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use time::format_description::well_known::Rfc3339;
use time::{Date, OffsetDateTime};

const CODEX_NEW_THREAD_BEFORE_MS: i64 = 60_000;
const CODEX_NEW_THREAD_AFTER_MS: i64 = 10 * 60_000;
const NEW_THREAD_DB_QUERY_LIMIT: usize = 200;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentRestoreResolveRequest {
    pub agent_kind: String,
    pub strategy: String,
    pub cwd: String,
    #[serde(default)]
    pub launch_started_at: Option<i64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentRestoreResolveResult {
    pub target: AgentRestoreTargetRecord,
    pub created_at_ms: Option<i64>,
    pub cwd: Option<String>,
    pub rollout_path: Option<String>,
    pub source: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentRestoreTargetRecord {
    pub kind: String,
    pub value: String,
}

#[derive(Debug, Clone)]
struct ThreadCandidate {
    id: String,
    created_at_ms: Option<i64>,
    updated_at_ms: Option<i64>,
    cwd: String,
    rollout_path: Option<PathBuf>,
    source: MatchSource,
}

#[derive(Debug, Clone, Copy)]
enum MatchSource {
    StateDb,
    Rollout,
}

pub fn resolve_agent_restore_target(
    request: AgentRestoreResolveRequest,
) -> Result<Option<AgentRestoreResolveResult>, String> {
    if request.agent_kind != "codex" {
        return Ok(None);
    }

    let codex_home = match resolve_codex_home() {
        Some(path) => path,
        None => return Ok(None),
    };
    let cwd = normalize_path_for_match(&request.cwd);

    let candidate = match request.strategy.as_str() {
        "codex_new_thread" => {
            let Some(launch_started_at) = request.launch_started_at else {
                return Ok(None);
            };
            find_codex_new_thread(&codex_home, &cwd, launch_started_at)
        }
        "codex_latest_cwd" => find_codex_latest_thread(&codex_home, &cwd),
        _ => return Ok(None),
    };

    Ok(candidate.map(candidate_to_result))
}

fn resolve_codex_home() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("CODEX_HOME")
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
    {
        return Some(path);
    }
    let mut home = dirs::home_dir()?;
    home.push(".codex");
    Some(home)
}

fn find_codex_new_thread(
    codex_home: &Path,
    cwd: &str,
    launch_started_at_ms: i64,
) -> Option<ThreadCandidate> {
    query_state_db_new_thread(codex_home, cwd, launch_started_at_ms)
        .or_else(|| scan_rollouts_for_new_thread(codex_home, cwd, launch_started_at_ms))
}

fn find_codex_latest_thread(codex_home: &Path, cwd: &str) -> Option<ThreadCandidate> {
    query_state_db_latest_thread(codex_home, cwd)
        .or_else(|| scan_rollouts_for_latest_thread(codex_home, cwd))
}

fn query_state_db_new_thread(
    codex_home: &Path,
    cwd: &str,
    launch_started_at_ms: i64,
) -> Option<ThreadCandidate> {
    let db_path = find_state_db_path(codex_home)?;
    let conn = open_state_db(&db_path).ok()?;
    let columns = table_columns(&conn, "threads").ok()?;
    let created_expr = time_expr(&columns, "created_at_ms", "created_at");
    let updated_expr = time_expr(&columns, "updated_at_ms", "updated_at");
    let lower_bound = launch_started_at_ms.saturating_sub(CODEX_NEW_THREAD_BEFORE_MS);
    let upper_bound = launch_started_at_ms.saturating_add(CODEX_NEW_THREAD_AFTER_MS);
    let sql = format!(
        "SELECT id, {created_expr} AS created_at_ms, {updated_expr} AS updated_at_ms, cwd, rollout_path \
         FROM threads \
         WHERE source = 'cli' AND archived = 0 AND {created_expr} BETWEEN ?1 AND ?2 \
         ORDER BY {created_expr} ASC LIMIT ?3"
    );

    let mut stmt = conn.prepare(&sql).ok()?;
    let rows = stmt
        .query_map(
            (lower_bound, upper_bound, NEW_THREAD_DB_QUERY_LIMIT as i64),
            state_db_candidate_from_row,
        )
        .ok()?;

    let candidate = rows
        .filter_map(Result::ok)
        .filter(|candidate| normalize_path_for_match(&candidate.cwd) == cwd)
        .min_by_key(|candidate| {
            candidate
                .created_at_ms
                .map(|created| (created as i128 - launch_started_at_ms as i128).abs())
                .unwrap_or(i128::MAX)
        });
    candidate
}

fn query_state_db_latest_thread(codex_home: &Path, cwd: &str) -> Option<ThreadCandidate> {
    let db_path = find_state_db_path(codex_home)?;
    let conn = open_state_db(&db_path).ok()?;
    let columns = table_columns(&conn, "threads").ok()?;
    let created_expr = time_expr(&columns, "created_at_ms", "created_at");
    let updated_expr = time_expr(&columns, "updated_at_ms", "updated_at");
    let sql = format!(
        "SELECT id, {created_expr} AS created_at_ms, {updated_expr} AS updated_at_ms, cwd, rollout_path \
         FROM threads \
         WHERE source = 'cli' AND archived = 0 \
         ORDER BY {updated_expr} DESC"
    );

    let mut stmt = conn.prepare(&sql).ok()?;
    let rows = stmt.query_map([], state_db_candidate_from_row).ok()?;

    let candidate = rows
        .filter_map(Result::ok)
        .find(|candidate| normalize_path_for_match(&candidate.cwd) == cwd);
    candidate
}

fn open_state_db(path: &Path) -> rusqlite::Result<Connection> {
    Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
}

fn find_state_db_path(codex_home: &Path) -> Option<PathBuf> {
    let mut versioned: Vec<(u32, PathBuf)> = fs::read_dir(codex_home)
        .ok()?
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let path = entry.path();
            let file_name = path.file_name()?.to_string_lossy();
            let version = file_name
                .strip_prefix("state_")?
                .strip_suffix(".sqlite")?
                .parse::<u32>()
                .ok()?;
            Some((version, path))
        })
        .collect();
    versioned.sort_by_key(|(version, _)| *version);
    if let Some((_, path)) = versioned.pop() {
        return Some(path);
    }

    let legacy = codex_home.join("state.sqlite");
    legacy.is_file().then_some(legacy)
}

fn table_columns(conn: &Connection, table: &str) -> rusqlite::Result<HashSet<String>> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
    Ok(rows.filter_map(Result::ok).collect())
}

fn time_expr(columns: &HashSet<String>, ms_column: &str, seconds_column: &str) -> String {
    if columns.contains(ms_column) {
        ms_column.to_string()
    } else {
        format!("{seconds_column} * 1000")
    }
}

fn state_db_candidate_from_row(row: &Row<'_>) -> rusqlite::Result<ThreadCandidate> {
    let rollout_path = row
        .get::<_, String>(4)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from);
    Ok(ThreadCandidate {
        id: row.get(0)?,
        created_at_ms: row.get(1).ok(),
        updated_at_ms: row.get(2).ok(),
        cwd: row.get(3)?,
        rollout_path,
        source: MatchSource::StateDb,
    })
}

fn scan_rollouts_for_new_thread(
    codex_home: &Path,
    cwd: &str,
    launch_started_at_ms: i64,
) -> Option<ThreadCandidate> {
    let lower_bound = launch_started_at_ms.saturating_sub(CODEX_NEW_THREAD_BEFORE_MS);
    let upper_bound = launch_started_at_ms.saturating_add(CODEX_NEW_THREAD_AFTER_MS);
    candidate_dates(lower_bound, upper_bound)
        .into_iter()
        .flat_map(|date| rollout_files_for_date(codex_home, date))
        .filter_map(read_rollout_candidate)
        .filter(|candidate| normalize_path_for_match(&candidate.cwd) == cwd)
        .filter(|candidate| {
            candidate
                .created_at_ms
                .is_some_and(|created| created >= lower_bound && created <= upper_bound)
        })
        .min_by_key(|candidate| {
            candidate
                .created_at_ms
                .map(|created| (created as i128 - launch_started_at_ms as i128).abs())
                .unwrap_or(i128::MAX)
        })
}

fn scan_rollouts_for_latest_thread(codex_home: &Path, cwd: &str) -> Option<ThreadCandidate> {
    collect_rollout_files(codex_home.join("sessions").as_path())
        .into_iter()
        .filter_map(read_rollout_candidate)
        .filter(|candidate| normalize_path_for_match(&candidate.cwd) == cwd)
        .max_by_key(|candidate| {
            candidate
                .updated_at_ms
                .or(candidate.created_at_ms)
                .unwrap_or(0)
        })
}

fn candidate_dates(lower_bound_ms: i64, upper_bound_ms: i64) -> Vec<Date> {
    let Some(start) = offset_datetime_from_millis(lower_bound_ms) else {
        return Vec::new();
    };
    let Some(end) = offset_datetime_from_millis(upper_bound_ms) else {
        return Vec::new();
    };

    let mut dates = Vec::new();
    let mut date = start.date();
    let end_date = end.date();
    loop {
        dates.push(date);
        if date >= end_date {
            break;
        }
        let Some(next) = date.next_day() else {
            break;
        };
        date = next;
    }
    dates
}

fn rollout_files_for_date(codex_home: &Path, date: Date) -> Vec<PathBuf> {
    let dir = codex_home
        .join("sessions")
        .join(format!("{:04}", date.year()))
        .join(format!("{:02}", u8::from(date.month())))
        .join(format!("{:02}", date.day()));
    read_rollout_files_in_dir(&dir)
}

fn collect_rollout_files(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    collect_rollout_files_inner(root, &mut out);
    out
}

fn collect_rollout_files_inner(root: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.filter_map(Result::ok) {
        let path = entry.path();
        if path.is_dir() {
            collect_rollout_files_inner(&path, out);
        } else if is_rollout_file(&path) {
            out.push(path);
        }
    }
}

fn read_rollout_files_in_dir(dir: &Path) -> Vec<PathBuf> {
    fs::read_dir(dir)
        .ok()
        .into_iter()
        .flat_map(|entries| entries.filter_map(Result::ok))
        .map(|entry| entry.path())
        .filter(|path| is_rollout_file(path))
        .collect()
}

fn is_rollout_file(path: &Path) -> bool {
    let Some(file_name) = path.file_name().map(|value| value.to_string_lossy()) else {
        return false;
    };
    file_name.starts_with("rollout-") && file_name.ends_with(".jsonl")
}

fn read_rollout_candidate(path: PathBuf) -> Option<ThreadCandidate> {
    let file = File::open(&path).ok()?;
    let reader = BufReader::new(file);
    let updated_at_ms = fs::metadata(&path)
        .ok()
        .and_then(|metadata| metadata.modified().ok())
        .and_then(|modified| modified.duration_since(std::time::UNIX_EPOCH).ok())
        .and_then(|duration| i64::try_from(duration.as_millis()).ok());

    for line in reader.lines().take(20).filter_map(Result::ok) {
        let value: Value = serde_json::from_str(&line).ok()?;
        if value.get("type").and_then(Value::as_str) != Some("session_meta") {
            continue;
        }
        let meta = value.get("payload").or_else(|| value.get("meta"))?;
        if let Some(source) = meta.get("source").and_then(Value::as_str) {
            if source != "cli" {
                return None;
            }
        }
        let id = meta.get("id").and_then(Value::as_str)?.to_string();
        let cwd = meta.get("cwd").and_then(Value::as_str)?.to_string();
        let created_at_ms = meta
            .get("timestamp")
            .and_then(Value::as_str)
            .and_then(parse_rfc3339_millis);
        return Some(ThreadCandidate {
            id,
            created_at_ms,
            updated_at_ms,
            cwd,
            rollout_path: Some(path),
            source: MatchSource::Rollout,
        });
    }

    None
}

fn parse_rfc3339_millis(value: &str) -> Option<i64> {
    let parsed = OffsetDateTime::parse(value, &Rfc3339).ok()?;
    let millis = parsed.unix_timestamp_nanos() / 1_000_000;
    i64::try_from(millis).ok()
}

fn offset_datetime_from_millis(ms: i64) -> Option<OffsetDateTime> {
    let seconds = ms.div_euclid(1000);
    let millis = ms.rem_euclid(1000);
    let datetime = OffsetDateTime::from_unix_timestamp(seconds).ok()?;
    datetime
        .replace_nanosecond(u32::try_from(millis * 1_000_000).ok()?)
        .ok()
}

fn candidate_to_result(candidate: ThreadCandidate) -> AgentRestoreResolveResult {
    AgentRestoreResolveResult {
        target: AgentRestoreTargetRecord {
            kind: "thread_id".to_string(),
            value: candidate.id,
        },
        created_at_ms: candidate.created_at_ms,
        cwd: Some(candidate.cwd),
        rollout_path: candidate
            .rollout_path
            .as_ref()
            .map(|path| path.display().to_string()),
        source: match candidate.source {
            MatchSource::StateDb => "state_db".to_string(),
            MatchSource::Rollout => "rollout".to_string(),
        },
    }
}

fn normalize_path_for_match(path: &str) -> String {
    let normalized_path = fs::canonicalize(path).unwrap_or_else(|_| PathBuf::from(path));
    let mut text = normalized_path.to_string_lossy().replace('\\', "/");
    while text.ends_with('/') && text.len() > 1 {
        text.pop();
    }
    if cfg!(windows) {
        text.make_ascii_lowercase();
    }
    text
}
