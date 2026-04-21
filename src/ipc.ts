import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  AgentKind,
  PersistedState,
  RestoreResolveStrategy,
  RestoreTarget,
} from "./types";
import type { PtySpawnOptions } from "./terminalConfig";

export type ExternalEditor = "vscode" | "zed";

export async function ptySpawn(
  projectId: string,
  cwd: string,
  rows: number,
  cols: number,
  options?: PtySpawnOptions
): Promise<string> {
  return invoke<string>("pty_spawn", { projectId, cwd, rows, cols, options });
}

export async function ptyWrite(sessionId: string, data: string): Promise<void> {
  await invoke("pty_write", { sessionId, data });
}

export interface PtyAttachSnapshot {
  data: string;
  lastSeq: number;
}

export async function ptyAttach(
  sessionId: string
): Promise<PtyAttachSnapshot> {
  return invoke<PtyAttachSnapshot>("pty_attach", { sessionId });
}

export async function ptyResize(
  sessionId: string,
  rows: number,
  cols: number
): Promise<void> {
  await invoke("pty_resize", { sessionId, rows, cols });
}

export async function ptyKill(sessionId: string): Promise<void> {
  await invoke("pty_kill", { sessionId });
}

export async function loadPersistedState(): Promise<PersistedState> {
  return invoke<PersistedState>("load_state");
}

export async function savePersistedState(state: PersistedState): Promise<void> {
  await invoke("save_state", { state });
}

export async function pathExists(path: string): Promise<boolean> {
  return invoke<boolean>("path_exists", { path });
}

export interface AgentRestoreResolveRequest {
  agentKind: AgentKind;
  strategy: RestoreResolveStrategy;
  cwd: string;
  launchStartedAt: number | null;
}

export interface AgentRestoreResolveResult {
  target: RestoreTarget;
  createdAtMs: number | null;
  cwd: string | null;
  rolloutPath: string | null;
  source: "state_db" | "rollout";
}

export async function resolveAgentRestoreTarget(
  request: AgentRestoreResolveRequest
): Promise<AgentRestoreResolveResult | null> {
  return invoke<AgentRestoreResolveResult | null>("resolve_agent_restore_target", {
    request,
  });
}

export async function openProjectInEditor(
  editor: ExternalEditor,
  path: string
): Promise<void> {
  await invoke("open_project_in_editor", { editor, path });
}

export async function openProjectInFileManager(path: string): Promise<void> {
  await invoke("open_project_in_file_manager", { path });
}

export interface PtyDataEvent {
  sessionId: string;
  data: string;
  seq: number;
}

export interface PtyExitEvent {
  sessionId: string;
  code: number;
}

export function onPtyData(
  cb: (e: PtyDataEvent) => void
): Promise<UnlistenFn> {
  return listen<PtyDataEvent>("pty://data", (e) => cb(e.payload));
}

export function onPtyExit(
  cb: (e: PtyExitEvent) => void
): Promise<UnlistenFn> {
  return listen<PtyExitEvent>("pty://exit", (e) => cb(e.payload));
}
