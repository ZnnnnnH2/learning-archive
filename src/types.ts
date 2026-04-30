export type ShellStatus =
  | "idle"
  | "running"
  | "waiting"
  | "error"
  | "exited";

export type ShellNameMode = "auto" | "manual";
export const AGENT_KINDS = ["codex", "claude", "gemini", "opencode"] as const;
export type AgentKind = (typeof AGENT_KINDS)[number];
export type LazyShellStartMode = "restore" | "new_agent_session" | "terminal";
export type AppLocale = "en" | "zh-CN";
export type RestoreDefaultsByAgent = Partial<
  Record<AgentKind, LazyShellStartMode>
>;
export type ShortcutActionId =
  | "terminal.copySelection"
  | "terminal.pasteClipboard"
  | "terminal.scrollToBottom"
  | "app.toggleSidebar"
  | "app.newShell"
  | "app.cloneShell"
  | "app.closeShell"
  | "app.focusShell1"
  | "app.focusShell2"
  | "app.focusShell3"
  | "app.focusShell4"
  | "app.focusShell5"
  | "app.focusShell6"
  | "app.focusShell7"
  | "app.focusShell8"
  | "app.focusShell9";

export interface ShortcutBindingConfig {
  bindings: string[];
  enabled: boolean;
}

export type ShortcutKeymap = Record<ShortcutActionId, ShortcutBindingConfig>;
export type PersistedShortcutKeymap = Partial<
  Record<ShortcutActionId, Partial<ShortcutBindingConfig> | null>
>;

export interface PersistedRestoreDefaultsByAgent {
  codex?: string | null;
  claude?: string | null;
  gemini?: string | null;
  opencode?: string | null;
}

export interface PersistedRestoreTarget {
  kind: string;
  value: string;
}

export interface Shell {
  id: string;
  updatedAt?: number;
  sessionId: string | null;
  projectId: string;
  name: string;
  autoName: string | null;
  nameMode: ShellNameMode;
  agentKind: AgentKind | null;
  agentLabel: string | null;
  resumeEntryCommand: string | null;
  newSessionCommand: string | null;
  startupCommand: string | null;
  lazyStart: boolean;
  taskSummary: string | null;
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
  updatedAt?: number;
  name: string;
  path: string;
  expanded: boolean;
  shellIds: string[];
}

export interface PersistedShell {
  id: string;
  updatedAt?: number | null;
  name: string;
  autoName?: string | null;
  nameMode?: string | null;
  agentKind?: string | null;
  agentLabel?: string | null;
  resumeEntryCommand?: string | null;
  newSessionCommand?: string | null;
  taskSummary?: string | null;
  // Backward compatibility for older persisted shells.
  restoreCapability?: string | null;
  restoreCommandPrefix?: string | null;
  restoreCommandSuffix?: string | null;
  restoreFallbackCommand?: string | null;
  restoreTarget?: PersistedRestoreTarget | null;
  restoreResolvePending?: boolean | null;
  restoreResolveStrategy?: string | null;
  restoreLaunchStartedAt?: number | null;
  restoreLaunchCwd?: string | null;
  resumeCommand?: string | null;
  firstMessagePreview?: string | null;
  terminalTitle?: string | null;
  cwd: string;
}

export interface PersistedProject {
  id: string;
  updatedAt?: number | null;
  name: string;
  path: string;
  shells: PersistedShell[];
}

export interface TerminalSettings {
  locale: AppLocale;
  shellExecutable: string;
  fontFamily: string;
  extraEnvText: string;
  alertPopupDurationSeconds: number;
  codexUseSelfSummaryTitle: boolean;
  restoreDefaultsByAgent: RestoreDefaultsByAgent;
  shortcutKeymap: ShortcutKeymap;
}

export interface PersistedTerminalSettings {
  locale?: string | null;
  shellExecutable?: string | null;
  fontFamily?: string | null;
  extraEnvText?: string | null;
  alertPopupDurationSeconds?: number | null;
  codexUseSelfSummaryTitle?: boolean | null;
  restoreDefaultsByAgent?: PersistedRestoreDefaultsByAgent | null;
  shortcutKeymap?: PersistedShortcutKeymap | null;
}

export interface PersistedState {
  projects: PersistedProject[];
  activeProjectId?: string | null;
  activeShellId?: string | null;
  sidebarWidth?: number | null;
  terminal?: PersistedTerminalSettings;
}
