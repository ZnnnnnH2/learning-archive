import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { PersistedState } from "./types";

export async function ptySpawn(
  projectId: string,
  cwd: string,
  rows: number,
  cols: number
): Promise<string> {
  return invoke<string>("pty_spawn", { projectId, cwd, rows, cols });
}

export async function ptyWrite(sessionId: string, data: string): Promise<void> {
  await invoke("pty_write", { sessionId, data });
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

export interface PtyDataEvent {
  sessionId: string;
  data: string;
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
