export type ShellStatus =
  | "idle"
  | "running"
  | "waiting"
  | "error"
  | "exited";

export interface Shell {
  id: string;
  sessionId: string | null;
  projectId: string;
  name: string;
  cwd: string;
  initialCwd: string;
  status: ShellStatus;
  hasUnread: boolean;
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
  cwd: string;
}

export interface PersistedProject {
  id: string;
  name: string;
  path: string;
  shells: PersistedShell[];
}

export interface PersistedState {
  projects: PersistedProject[];
  activeProjectId?: string | null;
  activeShellId?: string | null;
  sidebarWidth?: number | null;
}
