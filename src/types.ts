export type ShellStatus =
  | "idle"
  | "running"
  | "waiting"
  | "error"
  | "exited";

export type ShellNameMode = "auto" | "manual";
export type AgentKind = "codex" | "claude" | "gemini" | "opencode";
export type RestoreCapability =
  | "exact"
  | "recent"
  | "best_effort"
  | "unsupported";
export type RestoreTargetKind = "thread_id" | "session_id";
export type RestoreResolveStrategy = "codex_new_thread" | "codex_latest_cwd";

export interface RestoreTarget {
  kind: RestoreTargetKind;
  value: string;
}

export interface PersistedRestoreTarget {
  kind: string;
  value: string;
}

export interface Shell {
  id: string;
  sessionId: string | null;
  projectId: string;
  name: string;
  autoName: string | null;
  nameMode: ShellNameMode;
  agentKind: AgentKind | null;
  agentLabel: string | null;
  restoreCapability: RestoreCapability | null;
  restoreCommandPrefix: string | null;
  restoreCommandSuffix: string | null;
  restoreFallbackCommand: string | null;
  restoreTarget: RestoreTarget | null;
  restorePending: boolean;
  restoreResolvePending: boolean;
  restoreResolveStrategy: RestoreResolveStrategy | null;
  restoreLaunchStartedAt: number | null;
  restoreLaunchCwd: string | null;
  lazyStart: boolean;
  firstMessagePreview: string | null;
  terminalTitle: string | null;
  cwd: string;
  initialCwd: string;
  status: ShellStatus;
  needsAttention: boolean;
  lastExitCode: number | null;
  cols: number;
  rows: number;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  expanded: boolean;
  shellIds: string[];
}

export interface PersistedShell {
  id: string;
  name: string;
  autoName?: string | null;
  nameMode?: string | null;
  agentKind?: string | null;
  agentLabel?: string | null;
  restoreCapability?: string | null;
  restoreCommandPrefix?: string | null;
  restoreCommandSuffix?: string | null;
  restoreFallbackCommand?: string | null;
  restoreTarget?: PersistedRestoreTarget | null;
  restoreResolvePending?: boolean | null;
  restoreResolveStrategy?: string | null;
  restoreLaunchStartedAt?: number | null;
  restoreLaunchCwd?: string | null;
  // Backward compatibility for older persisted shells.
  resumeCommand?: string | null;
  firstMessagePreview?: string | null;
  terminalTitle?: string | null;
  cwd: string;
}

export interface PersistedProject {
  id: string;
  name: string;
  path: string;
  shells: PersistedShell[];
}

export interface TerminalSettings {
  shellExecutable: string;
  fontFamily: string;
  extraEnvText: string;
  alertPopupDurationSeconds: number;
}

export interface PersistedTerminalSettings {
  shellExecutable?: string | null;
  fontFamily?: string | null;
  extraEnvText?: string | null;
  alertPopupDurationSeconds?: number | null;
}

export interface PersistedState {
  projects: PersistedProject[];
  activeProjectId?: string | null;
  activeShellId?: string | null;
  sidebarWidth?: number | null;
  terminal?: PersistedTerminalSettings;
}
