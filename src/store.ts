import { create } from "zustand";
import {
  buildCodexSummaryShellName,
  buildDefaultAgentResumeEntryCommand,
  buildDefaultAgentNewSessionCommand,
  buildAgentShellName,
  buildDefaultShellName,
  detectAgentLaunchFromCommand,
  type DetectedAgentLaunch,
  normalizeShellNameMode,
} from "./autoName";
import {
  DEFAULT_TERMINAL_SETTINGS,
  normalizeTerminalSettings,
} from "./terminalConfig";
import {
  normalizeActivityTimestamp,
  sortProjectsByActivityDay,
  sortShellIdsByActivityDay,
} from "./activityOrdering";
import { areShortcutKeymapsEqual } from "./shortcuts";
import { AGENT_KINDS } from "./types";
import type {
  AgentKind,
  LazyShellStartMode,
  PersistedState,
  Project,
  RestoreDefaultsByAgent,
  Shell,
  ShellStatus,
  TerminalSettings,
} from "./types";
import { basename, newId } from "./utils";
import { ptyKill, savePersistedState } from "./ipc";

const PERSIST_DEBOUNCE_MS = 250;

let persistTimer: ReturnType<typeof setTimeout> | null = null;
let persistResolvers: Array<() => void> = [];

interface AppState {
  projects: Record<string, Project>;
  projectOrder: string[];
  shells: Record<string, Shell>;
  activeShellId: string | null;
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  terminalSettings: TerminalSettings;
  hydrated: boolean;

  addProject: (path: string, name?: string) => Project;
  removeProject: (id: string) => void;
  renameProject: (id: string, name: string) => void;
  toggleProjectExpand: (id: string) => void;
  reorderProjects: (order: string[]) => void;

  addShell: (projectId: string, opts?: { cwd?: string; name?: string }) => Shell;
  removeShell: (id: string) => void;
  renameShell: (id: string, name: string) => void;
  startShellAgentSession: (
    id: string,
    launch: DetectedAgentLaunch
  ) => void;
  clearShellStartupCommand: (id: string) => void;
  startLazyShell: (id: string, mode: LazyShellStartMode) => void;
  setShellTerminalTitle: (id: string, title: string) => void;
  setShellTaskSummary: (id: string, message: string) => void;
  useAutoShellName: (id: string) => void;
  cloneShell: (id: string) => Shell | null;
  setShellStatus: (id: string, status: ShellStatus) => void;
  setShellAttention: (id: string, v: boolean) => void;
  setShellCwd: (id: string, cwd: string) => void;
  setShellSize: (id: string, cols: number, rows: number) => void;
  setShellSession: (id: string, sessionId: string) => void;
  setShellExit: (id: string, code: number) => void;
  reorderShells: (projectId: string, order: string[]) => void;

  setActive: (id: string | null) => void;
  setSidebarWidth: (w: number) => void;
  toggleSidebar: () => void;
  setTerminalSettings: (settings: TerminalSettings) => void;
  getAgentRestoreDefault: (
    agentKind: AgentKind
  ) => LazyShellStartMode | undefined;
  setAgentRestoreDefault: (
    agentKind: AgentKind,
    mode: LazyShellStartMode
  ) => void;
  clearAgentRestoreDefault: (agentKind: AgentKind) => void;

  hydrateFrom: (state: PersistedState) => void;
  persist: () => Promise<void>;
}

const DEFAULT_SIDEBAR_WIDTH = 268;

function currentActivityTime(): number {
  return Date.now();
}

export const useAppStore = create<AppState>((set, get) => ({
  projects: {},
  projectOrder: [],
  shells: {},
  activeShellId: null,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
  sidebarCollapsed: false,
  terminalSettings: DEFAULT_TERMINAL_SETTINGS,
  hydrated: false,

  addProject: (path, name) => {
    const id = newId();
    const updatedAt = currentActivityTime();
    const project: Project = {
      id,
      updatedAt,
      name: name || basename(path) || path,
      path,
      expanded: true,
      shellIds: [],
    };
    set((s) => ({
      projects: { ...s.projects, [id]: project },
      projectOrder: [...s.projectOrder, id],
    }));
    // Auto-create one shell
    get().addShell(id);
    return project;
  },

  removeProject: (id) => {
    const { projects, shells, activeShellId } = get();
    const project = projects[id];
    if (!project) return;
    // Kill all PTYs under this project
    for (const sid of project.shellIds) {
      const s = shells[sid];
      if (s?.sessionId) ptyKill(s.sessionId).catch(() => {});
    }
    set((s) => {
      const nextProjects = { ...s.projects };
      delete nextProjects[id];
      const nextShells = { ...s.shells };
      for (const sid of project.shellIds) delete nextShells[sid];
      const nextOrder = s.projectOrder.filter((pid) => pid !== id);
      const nextActive = project.shellIds.includes(activeShellId ?? "")
        ? pickNextActive(nextShells, nextOrder, nextProjects)
        : s.activeShellId;
      return {
        projects: nextProjects,
        shells: nextShells,
        projectOrder: nextOrder,
        activeShellId: nextActive,
      };
    });
    get().persist();
  },

  renameProject: (id, name) => {
    set((s) => {
      const p = s.projects[id];
      if (!p) return {};
      if (p.name === name) return {};
      return {
        projects: {
          ...s.projects,
          [id]: { ...p, name, updatedAt: currentActivityTime() },
        },
      };
    });
    get().persist();
  },

  toggleProjectExpand: (id) => {
    set((s) => {
      const p = s.projects[id];
      if (!p) return {};
      return {
        projects: { ...s.projects, [id]: { ...p, expanded: !p.expanded } },
      };
    });
  },

  reorderProjects: (order) => {
    set({ projectOrder: order });
    get().persist();
  },

  addShell: (projectId, opts) => {
    const project = get().projects[projectId];
    if (!project) throw new Error("project not found: " + projectId);
    const id = newId();
    const updatedAt = currentActivityTime();
    const cwd = opts?.cwd ?? project.path;
    const idx = project.shellIds.length + 1;
    const autoName = opts?.name ?? buildDefaultShellName(idx);
    const shell: Shell = {
      id,
      updatedAt,
      sessionId: null,
      projectId,
      name: autoName,
      autoName,
      nameMode: "auto",
      agentKind: null,
      agentLabel: null,
      resumeEntryCommand: null,
      newSessionCommand: null,
      startupCommand: null,
      lazyStart: false,
      taskSummary: null,
      terminalTitle: null,
      cwd,
      initialCwd: cwd,
      status: "idle",
      needsAttention: false,
      lastExitCode: null,
      cols: 80,
      rows: 24,
    };
    set((s) => ({
      shells: { ...s.shells, [id]: shell },
      projects: {
        ...s.projects,
        [projectId]: {
          ...project,
          updatedAt,
          expanded: true,
          shellIds: [...project.shellIds, id],
        },
      },
      activeShellId: id,
    }));
    get().persist();
    return shell;
  },

  removeShell: (id) => {
    const { shells, activeShellId } = get();
    const sh = shells[id];
    if (!sh) return;
    if (sh.sessionId) ptyKill(sh.sessionId).catch(() => {});
    set((s) => {
      const nextShells = { ...s.shells };
      delete nextShells[id];
      const proj = s.projects[sh.projectId];
      const nextProjects = proj
        ? {
            ...s.projects,
            [sh.projectId]: {
              ...proj,
              updatedAt: currentActivityTime(),
              shellIds: proj.shellIds.filter((x) => x !== id),
            },
          }
        : s.projects;
      const nextActive =
        activeShellId === id
          ? pickNextActive(nextShells, s.projectOrder, nextProjects)
          : activeShellId;
      return {
        shells: nextShells,
        projects: nextProjects,
        activeShellId: nextActive,
      };
    });
    get().persist();
  },

  renameShell: (id, name) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      if (sh.name === name && sh.nameMode === "manual") return {};
      return {
        shells: {
          ...s.shells,
          [id]: {
            ...sh,
            name,
            nameMode: "manual",
            updatedAt: currentActivityTime(),
          },
        },
      };
    });
    get().persist();
  },

  startShellAgentSession: (id, launch) => {
    const nextLabel = launch.label.trim();
    if (!nextLabel) return;

    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      const nextShell = syncShellAutoName(
        {
          ...sh,
          agentKind: launch.kind,
          agentLabel: nextLabel,
          resumeEntryCommand:
            normalizeNullableString(launch.resumeEntryCommand) ??
            buildDefaultAgentResumeEntryCommand(launch.kind),
          newSessionCommand:
            normalizeNullableString(launch.newSessionCommand) ??
            buildDefaultAgentNewSessionCommand(launch.kind),
          startupCommand: null,
          taskSummary: null,
          terminalTitle: null,
          updatedAt: currentActivityTime(),
        },
        s.sidebarWidth,
        s.terminalSettings.codexUseSelfSummaryTitle
      );
      if (
        areShellNameFieldsEqual(sh, nextShell) &&
        areShellRestoreFieldsEqual(sh, nextShell)
      ) {
        return {};
      }

      return {
        shells: {
          ...s.shells,
          [id]: nextShell,
        },
      };
    });
    get().persist();
  },

  clearShellStartupCommand: (id) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh || !sh.startupCommand) return {};
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, startupCommand: null },
        },
      };
    });
    get().persist();
  },

  startLazyShell: (id, mode) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};

      const nextShellBase: Shell = {
        ...sh,
        updatedAt: currentActivityTime(),
        lazyStart: false,
        startupCommand: null,
      };

      let nextShell = nextShellBase;
      if (mode === "restore" && sh.resumeEntryCommand) {
        nextShell = {
          ...nextShellBase,
          startupCommand: sh.resumeEntryCommand,
          status: "idle",
        };
      } else if (mode === "new_agent_session") {
        nextShell = {
          ...nextShellBase,
          taskSummary: null,
          terminalTitle: null,
          status: "idle",
          startupCommand:
            sh.newSessionCommand ?? buildDefaultAgentNewSessionCommand(sh.agentKind),
        };
      } else {
        nextShell = {
          ...nextShellBase,
          agentKind: null,
          agentLabel: null,
          resumeEntryCommand: null,
          newSessionCommand: null,
          taskSummary: null,
          terminalTitle: null,
          status: "idle",
        };
      }

      nextShell = syncShellAutoName(
        nextShell,
        s.sidebarWidth,
        s.terminalSettings.codexUseSelfSummaryTitle
      );

      if (
        nextShell === sh ||
        (sh.lazyStart === nextShell.lazyStart &&
          areShellRestoreFieldsEqual(sh, nextShell) &&
          sh.startupCommand === nextShell.startupCommand &&
          areShellNameFieldsEqual(sh, nextShell) &&
          sh.status === nextShell.status)
      ) {
        return {
          activeShellId: id,
        };
      }

      return {
        activeShellId: id,
        shells: {
          ...s.shells,
          [id]: nextShell,
        },
      };
    });
    get().persist();
  },

  setShellTerminalTitle: (id, title) => {
    const nextTitle = normalizeTerminalTitle(title);
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      const nextShell = syncShellAutoName(
        {
          ...sh,
          terminalTitle: nextTitle,
          updatedAt: currentActivityTime(),
        },
        s.sidebarWidth,
        s.terminalSettings.codexUseSelfSummaryTitle
      );
      if (areShellNameFieldsEqual(sh, nextShell)) return {};
      return {
        shells: {
          ...s.shells,
          [id]: nextShell,
        },
      };
    });
    get().persist();
  },

  setShellTaskSummary: (id, message) => {
    const nextMessage = message.trim();
    if (!nextMessage) return;

    set((s) => {
      const sh = s.shells[id];
      if (!sh || !sh.agentLabel) return {};
      const nextShell = syncShellAutoName(
        {
          ...sh,
          taskSummary: nextMessage,
          updatedAt: currentActivityTime(),
        },
        s.sidebarWidth,
        s.terminalSettings.codexUseSelfSummaryTitle
      );
      if (areShellNameFieldsEqual(sh, nextShell)) return {};
      return {
        shells: {
          ...s.shells,
          [id]: nextShell,
        },
      };
    });
    get().persist();
  },

  useAutoShellName: (id) => {
    set((s) => {
      const sh = s.shells[id];
      const nextName = sh?.autoName?.trim();
      if (!sh || !nextName) return {};
      if (sh.name === nextName && sh.nameMode === "auto") return {};
      return {
        shells: {
          ...s.shells,
          [id]: {
            ...sh,
            name: nextName,
            nameMode: "auto",
            updatedAt: currentActivityTime(),
          },
        },
      };
    });
    get().persist();
  },

  cloneShell: (id) => {
    const sh = get().shells[id];
    if (!sh) return null;
    return get().addShell(sh.projectId, { cwd: sh.cwd });
  },

  setShellStatus: (id, status) =>
    set((s) => {
      const sh = s.shells[id];
      if (!sh || sh.status === status) return {};
      return { shells: { ...s.shells, [id]: { ...sh, status } } };
    }),

  setShellAttention: (id, v) =>
    set((s) => {
      const sh = s.shells[id];
      if (!sh || sh.needsAttention === v) return {};
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, needsAttention: v },
        },
      };
    }),

  setShellCwd: (id, cwd) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh || sh.cwd === cwd) return {};
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, cwd, updatedAt: currentActivityTime() },
        },
      };
    });
    get().persist();
  },

  setShellSize: (id, cols, rows) =>
    set((s) => {
      const sh = s.shells[id];
      if (!sh || (sh.cols === cols && sh.rows === rows)) return {};
      return { shells: { ...s.shells, [id]: { ...sh, cols, rows } } };
    }),

  setShellSession: (id, sessionId) =>
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, sessionId, lazyStart: false },
        },
      };
    }),

  setShellExit: (id, code) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      return {
        shells: {
          ...s.shells,
          [id]: {
            ...sh,
            updatedAt: currentActivityTime(),
            sessionId: null,
            lazyStart: false,
            lastExitCode: code,
            status: code === 0 ? "exited" : "error",
          },
        },
      };
    });
    get().persist();
  },

  reorderShells: (projectId, order) => {
    set((s) => {
      const p = s.projects[projectId];
      if (!p) return {};
      return {
        projects: {
          ...s.projects,
          [projectId]: { ...p, shellIds: order },
        },
      };
    });
    get().persist();
  },

  setActive: (id) => {
    set(() => {
      if (!id) {
        return { activeShellId: null };
      }
      return { activeShellId: id };
    });
    if (id) {
      const sh = get().shells[id];
      if (sh?.needsAttention) {
        get().setShellAttention(id, false);
      }
    }
    get().persist();
  },

  setSidebarWidth: (w) => {
    const nextWidth = Math.max(180, Math.min(560, w));
    set((s) => {
      const nextShells: Record<string, Shell> = {};
      let changed = s.sidebarWidth !== nextWidth;

      for (const [id, sh] of Object.entries(s.shells)) {
        const nextShell = syncShellAutoName(
          sh,
          nextWidth,
          s.terminalSettings.codexUseSelfSummaryTitle
        );
        nextShells[id] = nextShell;
        if (!changed && !areShellNameFieldsEqual(sh, nextShell)) {
          changed = true;
        }
      }

      if (!changed) return {};
      return {
        sidebarWidth: nextWidth,
        shells: nextShells,
      };
    });
    get().persist();
  },

  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setTerminalSettings: (settings) => {
    const normalized = normalizeTerminalSettings(settings);
    set((s) => {
      const nextShells: Record<string, Shell> = {};
      let shellNamesChanged = false;

      for (const [id, sh] of Object.entries(s.shells)) {
        const nextShell = syncShellAutoName(
          sh,
          s.sidebarWidth,
          normalized.codexUseSelfSummaryTitle
        );
        nextShells[id] = nextShell;
        if (!shellNamesChanged && !areShellNameFieldsEqual(sh, nextShell)) {
          shellNamesChanged = true;
        }
      }

      if (!shellNamesChanged && areTerminalSettingsEqual(s.terminalSettings, normalized)) {
        return {};
      }

      return {
        terminalSettings: normalized,
        ...(shellNamesChanged ? { shells: nextShells } : {}),
      };
    });
    get().persist();
  },

  getAgentRestoreDefault: (agentKind) =>
    get().terminalSettings.restoreDefaultsByAgent[agentKind],

  setAgentRestoreDefault: (agentKind, mode) => {
    set((s) => {
      const nextTerminalSettings = normalizeTerminalSettings({
        ...s.terminalSettings,
        restoreDefaultsByAgent: {
          ...s.terminalSettings.restoreDefaultsByAgent,
          [agentKind]: mode,
        },
      });
      if (areTerminalSettingsEqual(s.terminalSettings, nextTerminalSettings)) {
        return {};
      }
      return {
        terminalSettings: nextTerminalSettings,
      };
    });
    get().persist();
  },

  clearAgentRestoreDefault: (agentKind) => {
    set((s) => {
      const nextRestoreDefaultsByAgent = removeAgentRestoreDefault(
        s.terminalSettings.restoreDefaultsByAgent,
        agentKind
      );
      if (
        nextRestoreDefaultsByAgent === s.terminalSettings.restoreDefaultsByAgent
      ) {
        return {};
      }
      return {
        terminalSettings: normalizeTerminalSettings({
          ...s.terminalSettings,
          restoreDefaultsByAgent: nextRestoreDefaultsByAgent,
        }),
      };
    });
    get().persist();
  },

  hydrateFrom: (state) => {
    const projects: Record<string, Project> = {};
    const shells: Record<string, Shell> = {};
    const projectOrder: string[] = [];
    const sidebarWidth = state.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH;
    const terminalSettings = normalizeTerminalSettings(state.terminal);
    for (const p of state.projects ?? []) {
      const shellIds: string[] = [];
      for (const s of p.shells ?? []) {
        const nameMode = normalizeShellNameMode(s.nameMode, s.name);
        const agentKind =
          normalizeAgentKind(s.agentKind) ??
          inferAgentKindFromLabel(s.agentLabel ?? null);
        const migratedCommands = resolvePersistedAgentCommands(s, agentKind);
        const hydratedShell = syncShellAutoName(
          {
            id: s.id,
            updatedAt: normalizeActivityTimestamp(s.updatedAt),
            sessionId: null,
            projectId: p.id,
            name: s.name,
            autoName: s.autoName ?? (nameMode === "auto" ? s.name : null),
            nameMode,
            agentKind,
            agentLabel: s.agentLabel ?? null,
            resumeEntryCommand: migratedCommands.resumeEntryCommand,
            newSessionCommand: migratedCommands.newSessionCommand,
            startupCommand: null,
            lazyStart: true,
            taskSummary:
              normalizeNullableString(s.taskSummary) ??
              normalizeNullableString(s.firstMessagePreview),
            terminalTitle: normalizeTerminalTitle(s.terminalTitle),
            cwd: s.cwd,
            initialCwd: s.cwd,
            status: "idle",
            needsAttention: false,
            lastExitCode: null,
            cols: 80,
            rows: 24,
          },
          sidebarWidth,
          terminalSettings.codexUseSelfSummaryTitle
        );
        shells[s.id] = {
          ...hydratedShell,
          id: s.id,
        };
        shellIds.push(s.id);
      }
      projects[p.id] = {
        id: p.id,
        updatedAt: normalizeActivityTimestamp(p.updatedAt),
        name: p.name,
        path: p.path,
        expanded: true,
        shellIds: sortShellIdsByActivityDay(shellIds, shells),
      };
      projectOrder.push(p.id);
    }
    const sortedProjectOrder = sortProjectsByActivityDay(
      projectOrder,
      projects,
      shells
    );
    const active =
      (state.activeShellId && shells[state.activeShellId]?.id) ||
      sortedProjectOrder
        .map((pid) => projects[pid].shellIds[0])
        .find(Boolean) ||
      null;
    set({
      projects,
      shells,
      projectOrder: sortedProjectOrder,
      activeShellId: active,
      sidebarWidth,
      terminalSettings,
      hydrated: true,
    });
  },

  persist: () => {
    const s = get();
    if (!s.hydrated) return Promise.resolve();
    const snapshot: PersistedState = {
      projects: s.projectOrder.map((pid) => {
        const p = s.projects[pid];
        return {
          id: p.id,
          updatedAt: p.updatedAt,
          name: p.name,
          path: p.path,
          shells: p.shellIds.map((sid) => {
            const sh = s.shells[sid];
            return {
              id: sh.id,
              updatedAt: sh.updatedAt,
              name: sh.name,
              autoName: sh.autoName,
              nameMode: sh.nameMode,
              agentKind: sh.agentKind,
              agentLabel: sh.agentLabel,
              resumeEntryCommand: sh.resumeEntryCommand,
              newSessionCommand: sh.newSessionCommand,
              taskSummary: sh.taskSummary,
              terminalTitle: sh.terminalTitle,
              cwd: sh.cwd || sh.initialCwd,
            };
          }),
        };
      }),
      activeShellId: s.activeShellId,
      sidebarWidth: s.sidebarWidth,
      terminal: s.terminalSettings,
    };
    return schedulePersist(snapshot);
  },
}));

function schedulePersist(snapshot: PersistedState): Promise<void> {
  if (persistTimer !== null) {
    clearTimeout(persistTimer);
  }

  return new Promise((resolve) => {
    persistResolvers.push(resolve);
    persistTimer = setTimeout(async () => {
      persistTimer = null;
      const resolvers = persistResolvers;
      persistResolvers = [];
      try {
        await savePersistedState(snapshot);
      } catch (e) {
        console.warn("persist failed", e);
      } finally {
        for (const resolver of resolvers) resolver();
      }
    }, PERSIST_DEBOUNCE_MS);
  });
}

function pickNextActive(
  shells: Record<string, Shell>,
  projectOrder: string[],
  projects: Record<string, Project>
): string | null {
  for (const pid of projectOrder) {
    const p = projects[pid];
    if (!p) continue;
    for (const sid of p.shellIds) {
      if (shells[sid]) return sid;
    }
  }
  return null;
}

function syncShellAutoName(
  shell: Shell,
  sidebarWidth: number,
  codexUseSelfSummaryTitle: boolean
): Shell {
  const terminalTitle = normalizeTerminalTitle(shell.terminalTitle);
  const fallbackName = shell.autoName ?? shell.name;
  const codexSummaryTitle =
    shell.agentKind === "codex" && codexUseSelfSummaryTitle
      ? buildCodexSummaryShellName(
          shell.taskSummary,
          terminalTitle,
          sidebarWidth
        )
      : null;
  const autoName =
    codexSummaryTitle
      ? codexSummaryTitle
      : terminalTitle
        ? terminalTitle
      : buildAgentShellName(
          shell.agentLabel,
          shell.taskSummary,
          fallbackName,
          sidebarWidth
        );
  return {
    ...shell,
    terminalTitle,
    autoName,
    name: shell.nameMode === "auto" ? autoName : shell.name,
  };
}

function areShellNameFieldsEqual(a: Shell, b: Shell): boolean {
  return (
    a.name === b.name &&
    a.autoName === b.autoName &&
    a.nameMode === b.nameMode &&
    a.agentKind === b.agentKind &&
    a.agentLabel === b.agentLabel &&
    a.taskSummary === b.taskSummary &&
    a.terminalTitle === b.terminalTitle
  );
}

function areShellRestoreFieldsEqual(a: Shell, b: Shell): boolean {
  return (
    a.agentKind === b.agentKind &&
    a.resumeEntryCommand === b.resumeEntryCommand &&
    a.newSessionCommand === b.newSessionCommand &&
    a.startupCommand === b.startupCommand &&
    a.lazyStart === b.lazyStart
  );
}

function normalizeTerminalTitle(title: string | null | undefined): string | null {
  const normalized = title?.trim() ?? "";
  return normalized || null;
}

function areTerminalSettingsEqual(
  a: TerminalSettings,
  b: TerminalSettings
): boolean {
  return (
    a.locale === b.locale &&
    a.shellExecutable === b.shellExecutable &&
    a.fontFamily === b.fontFamily &&
    a.extraEnvText === b.extraEnvText &&
    a.alertPopupDurationSeconds === b.alertPopupDurationSeconds &&
    a.codexUseSelfSummaryTitle === b.codexUseSelfSummaryTitle &&
    areRestoreDefaultsByAgentEqual(
      a.restoreDefaultsByAgent,
      b.restoreDefaultsByAgent
    ) &&
    areShortcutKeymapsEqual(a.shortcutKeymap, b.shortcutKeymap)
  );
}

function normalizeNullableString(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function normalizeAgentKind(value: string | null | undefined): AgentKind | null {
  if (value && AGENT_KINDS.includes(value as AgentKind)) {
    return value as AgentKind;
  }
  return null;
}

function inferAgentKindFromLabel(label: string | null): AgentKind | null {
  const normalized = label?.trim().toLowerCase();
  if (normalized === "codex") return "codex";
  if (normalized === "claude") return "claude";
  if (normalized === "gemini") return "gemini";
  if (normalized === "opencode") return "opencode";
  return null;
}

function resolvePersistedAgentCommands(
  shell: PersistedState["projects"][number]["shells"][number],
  agentKind: AgentKind | null
): {
  resumeEntryCommand: string | null;
  newSessionCommand: string | null;
} {
  const persistedResumeEntryCommand = normalizeNullableString(
    shell.resumeEntryCommand
  );
  const persistedNewSessionCommand = normalizeNullableString(
    shell.newSessionCommand
  );

  if (persistedResumeEntryCommand || persistedNewSessionCommand) {
    return {
      resumeEntryCommand:
        persistedResumeEntryCommand ??
        inferResumeEntryCommandFromCommand(
          persistedNewSessionCommand,
          shell.cwd,
          agentKind
        ) ??
        buildDefaultAgentResumeEntryCommand(agentKind),
      newSessionCommand:
        persistedNewSessionCommand ??
        inferNewSessionCommandFromCommand(
          persistedResumeEntryCommand,
          shell.cwd,
          agentKind
        ) ??
        buildDefaultAgentNewSessionCommand(agentKind),
    };
  }

  const legacyCandidates = [
    normalizeNullableString(shell.newSessionCommand),
    normalizeNullableString(shell.restoreFallbackCommand),
    buildLegacyCodexResumeCommand(shell),
    normalizeNullableString(shell.resumeCommand),
  ];

  for (const candidate of legacyCandidates) {
    const launch = inferLaunchFromCommand(candidate, shell.cwd, agentKind);
    if (!launch) continue;
    return {
      resumeEntryCommand:
        normalizeNullableString(launch.resumeEntryCommand) ??
        buildDefaultAgentResumeEntryCommand(launch.kind),
      newSessionCommand:
        normalizeNullableString(launch.newSessionCommand) ??
        buildDefaultAgentNewSessionCommand(launch.kind),
    };
  }

  return {
    resumeEntryCommand: buildDefaultAgentResumeEntryCommand(agentKind),
    newSessionCommand: buildDefaultAgentNewSessionCommand(agentKind),
  };
}

function inferResumeEntryCommandFromCommand(
  command: string | null,
  cwd: string,
  expectedKind: AgentKind | null
): string | null {
  return inferLaunchFromCommand(command, cwd, expectedKind)?.resumeEntryCommand ?? null;
}

function inferNewSessionCommandFromCommand(
  command: string | null,
  cwd: string,
  expectedKind: AgentKind | null
): string | null {
  return inferLaunchFromCommand(command, cwd, expectedKind)?.newSessionCommand ?? null;
}

function inferLaunchFromCommand(
  command: string | null,
  cwd: string,
  expectedKind: AgentKind | null
): DetectedAgentLaunch | null {
  if (!command) return null;
  const launch = detectAgentLaunchFromCommand(command, cwd);
  if (!launch) return null;
  if (expectedKind && launch.kind !== expectedKind) return null;
  return launch;
}

function buildLegacyCodexResumeCommand(
  shell: PersistedState["projects"][number]["shells"][number]
): string | null {
  const prefix = normalizeNullableString(shell.restoreCommandPrefix);
  const suffix = normalizeNullableString(shell.restoreCommandSuffix);
  if (!prefix) return null;
  return [prefix, suffix].filter(Boolean).join(" ").trim() || null;
}

function areRestoreDefaultsByAgentEqual(
  a: RestoreDefaultsByAgent,
  b: RestoreDefaultsByAgent
): boolean {
  return AGENT_KINDS.every((agentKind) => a[agentKind] === b[agentKind]);
}

function removeAgentRestoreDefault(
  restoreDefaultsByAgent: RestoreDefaultsByAgent,
  agentKind: AgentKind
): RestoreDefaultsByAgent {
  if (!(agentKind in restoreDefaultsByAgent)) {
    return restoreDefaultsByAgent;
  }
  const nextRestoreDefaultsByAgent = { ...restoreDefaultsByAgent };
  delete nextRestoreDefaultsByAgent[agentKind];
  return nextRestoreDefaultsByAgent;
}

type AppStoreState = ReturnType<typeof useAppStore.getState>;

export const selectRestoreDefaultsByAgent = (state: AppStoreState) =>
  state.terminalSettings.restoreDefaultsByAgent;

export const selectAgentRestoreDefault =
  (agentKind: AgentKind) =>
  (state: AppStoreState): LazyShellStartMode | undefined =>
    state.terminalSettings.restoreDefaultsByAgent[agentKind];
