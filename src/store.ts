import { create } from "zustand";
import {
  buildDefaultAgentNewSessionCommand,
  buildAgentShellName,
  buildDefaultShellName,
  sanitizeAgentRestoreCommandPrefix,
  type DetectedAgentLaunch,
  normalizeShellNameMode,
} from "./autoName";
import {
  DEFAULT_TERMINAL_SETTINGS,
  normalizeTerminalSettings,
} from "./terminalConfig";
import type {
  AgentKind,
  LazyShellStartMode,
  PersistedRestoreTarget,
  PersistedState,
  Project,
  RestoreCapability,
  RestoreResolveStrategy,
  RestoreTarget,
  Shell,
  ShellStatus,
  TerminalSettings,
} from "./types";
import { basename, newId } from "./utils";
import { ptyKill, savePersistedState } from "./ipc";

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
    launch: DetectedAgentLaunch,
    launchedAt: number
  ) => void;
  setShellRestoreTarget: (
    id: string,
    target: RestoreTarget,
    expectedLaunchStartedAt?: number | null
  ) => void;
  markShellRestoreResolveFailed: (
    id: string,
    expectedLaunchStartedAt?: number | null
  ) => void;
  clearShellRestorePending: (id: string) => void;
  clearShellStartupCommand: (id: string) => void;
  startLazyShell: (id: string, mode: LazyShellStartMode) => void;
  setShellTerminalTitle: (id: string, title: string) => void;
  setShellFirstMessagePreview: (id: string, message: string) => void;
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

  hydrateFrom: (state: PersistedState) => void;
  persist: () => Promise<void>;
}

const DEFAULT_SIDEBAR_WIDTH = 268;

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
    const project: Project = {
      id,
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
      return { projects: { ...s.projects, [id]: { ...p, name } } };
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
    const cwd = opts?.cwd ?? project.path;
    const idx = project.shellIds.length + 1;
    const autoName = opts?.name ?? buildDefaultShellName(idx);
    const shell: Shell = {
      id,
      sessionId: null,
      projectId,
      name: autoName,
      autoName,
      nameMode: "auto",
      agentKind: null,
      agentLabel: null,
      restoreCapability: null,
      restoreCommandPrefix: null,
      restoreCommandSuffix: null,
      restoreFallbackCommand: null,
      newSessionCommand: null,
      startupCommand: null,
      restoreTarget: null,
      restorePending: false,
      restoreResolvePending: false,
      restoreResolveStrategy: null,
      restoreLaunchStartedAt: null,
      restoreLaunchCwd: null,
      lazyStart: false,
      firstMessagePreview: null,
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
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, name, nameMode: "manual" },
        },
      };
    });
    get().persist();
  },

  startShellAgentSession: (id, launch, launchedAt) => {
    const nextLabel = launch.label.trim();
    if (!nextLabel) return;
    const restoreTarget = normalizeRestoreTarget(launch.explicitRestoreTarget);
    const resolvePending = Boolean(launch.resolveStrategy && !restoreTarget);

    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      const nextShell = syncShellAutoName(
        {
          ...sh,
          agentKind: launch.kind,
          agentLabel: nextLabel,
          restoreCapability: launch.restoreCapability,
          restoreCommandPrefix: sanitizeAgentRestoreCommandPrefix(
            launch.kind,
            normalizeNullableString(launch.restoreCommandPrefix)
          ),
          restoreCommandSuffix: normalizeNullableString(
            launch.restoreCommandSuffix
          ),
          restoreFallbackCommand: normalizeNullableString(
            launch.restoreFallbackCommand
          ),
          newSessionCommand:
            normalizeNullableString(launch.newSessionCommand) ??
            buildDefaultAgentNewSessionCommand(launch.kind),
          startupCommand: null,
          restoreTarget,
          restorePending: false,
          restoreResolvePending: resolvePending,
          restoreResolveStrategy: launch.resolveStrategy,
          restoreLaunchStartedAt: resolvePending ? launchedAt : null,
          restoreLaunchCwd: normalizeNullableString(launch.launchCwd),
          firstMessagePreview: null,
          terminalTitle: null,
        },
        s.sidebarWidth
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

  setShellRestoreTarget: (id, target, expectedLaunchStartedAt) => {
    const nextTarget = normalizeRestoreTarget(target);
    if (!nextTarget) return;

    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};
      if (
        expectedLaunchStartedAt != null &&
        sh.restoreLaunchStartedAt !== expectedLaunchStartedAt
      ) {
        return {};
      }
      const nextShell: Shell = {
        ...sh,
        restoreTarget: nextTarget,
        restoreResolvePending: false,
      };
      if (areShellRestoreFieldsEqual(sh, nextShell)) return {};
      return {
        shells: {
          ...s.shells,
          [id]: nextShell,
        },
      };
    });
    get().persist();
  },

  markShellRestoreResolveFailed: (id, expectedLaunchStartedAt) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh || !sh.restoreResolvePending) return {};
      if (
        expectedLaunchStartedAt != null &&
        sh.restoreLaunchStartedAt !== expectedLaunchStartedAt
      ) {
        return {};
      }
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, restoreResolvePending: false },
        },
      };
    });
    get().persist();
  },

  clearShellRestorePending: (id) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh || !sh.restorePending) return {};
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, restorePending: false },
        },
      };
    });
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
  },

  startLazyShell: (id, mode) => {
    set((s) => {
      const sh = s.shells[id];
      if (!sh) return {};

      const hasRestorePath = Boolean(
        sh.restorePending ||
          sh.restoreResolvePending ||
          sh.restoreTarget ||
          sh.restoreFallbackCommand
      );
      const nextShellBase: Shell = {
        ...sh,
        lazyStart: false,
        startupCommand: null,
      };

      let nextShell = nextShellBase;
      if (mode === "restore" && hasRestorePath) {
        nextShell = {
          ...nextShellBase,
          restorePending: Boolean(
            sh.restorePending ||
              sh.restoreResolvePending ||
              sh.restoreTarget ||
              sh.restoreFallbackCommand
          ),
        };
      } else if (mode === "new_agent_session") {
        nextShell = {
          ...nextShellBase,
          restoreCapability: null,
          restoreCommandPrefix: null,
          restoreCommandSuffix: null,
          restoreFallbackCommand: null,
          restoreTarget: null,
          restorePending: false,
          restoreResolvePending: false,
          restoreResolveStrategy: null,
          restoreLaunchStartedAt: null,
          restoreLaunchCwd: null,
          firstMessagePreview: null,
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
          restoreCapability: null,
          restoreCommandPrefix: null,
          restoreCommandSuffix: null,
          restoreFallbackCommand: null,
          newSessionCommand: null,
          restoreTarget: null,
          restorePending: false,
          restoreResolvePending: false,
          restoreResolveStrategy: null,
          restoreLaunchStartedAt: null,
          restoreLaunchCwd: null,
          firstMessagePreview: null,
          terminalTitle: null,
          status: "idle",
        };
      }

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
        },
        s.sidebarWidth
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

  setShellFirstMessagePreview: (id, message) => {
    const nextMessage = message.trim();
    if (!nextMessage) return;

    set((s) => {
      const sh = s.shells[id];
      if (!sh || !sh.agentLabel) return {};
      const nextShell = syncShellAutoName(
        {
          ...sh,
          firstMessagePreview: nextMessage,
        },
        s.sidebarWidth
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
      return {
        shells: {
          ...s.shells,
          [id]: { ...sh, name: nextName, nameMode: "auto" },
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
      return { shells: { ...s.shells, [id]: { ...sh, cwd } } };
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
            sessionId: null,
            lazyStart: false,
            lastExitCode: code,
            status: code === 0 ? "exited" : "error",
          },
        },
      };
    });
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
        const nextShell = syncShellAutoName(sh, nextWidth);
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
    set({ terminalSettings: normalizeTerminalSettings(settings) });
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
        const restoreTarget = normalizeRestoreTarget(s.restoreTarget);
        const restoreFallbackCommand =
          normalizeNullableString(s.restoreFallbackCommand) ??
          normalizeNullableString(s.resumeCommand);
        const newSessionCommand =
          normalizeNullableString(s.newSessionCommand) ??
          buildDefaultAgentNewSessionCommand(agentKind);
        const restoreCommandPrefix = sanitizeAgentRestoreCommandPrefix(
          agentKind,
          normalizeNullableString(s.restoreCommandPrefix)
        );
        const restoreResolveStrategy = normalizeRestoreResolveStrategy(
          s.restoreResolveStrategy
        );
        const restoreResolvePending = Boolean(
          !restoreTarget &&
            s.restoreResolvePending &&
            restoreResolveStrategy &&
            s.restoreLaunchStartedAt
        );
        const hydratedShell = syncShellAutoName(
          {
            id: s.id,
            sessionId: null,
            projectId: p.id,
            name: s.name,
            autoName: s.autoName ?? (nameMode === "auto" ? s.name : null),
            nameMode,
            agentKind,
            agentLabel: s.agentLabel ?? null,
            restoreCapability:
              normalizeRestoreCapability(s.restoreCapability) ??
              inferRestoreCapability(agentKind, restoreTarget, restoreFallbackCommand),
            restoreCommandPrefix,
            restoreCommandSuffix: normalizeNullableString(
              s.restoreCommandSuffix
            ),
            restoreFallbackCommand,
            newSessionCommand,
            startupCommand: null,
            restoreTarget,
            restorePending: Boolean(restoreTarget || restoreFallbackCommand),
            restoreResolvePending,
            restoreResolveStrategy,
            restoreLaunchStartedAt:
              typeof s.restoreLaunchStartedAt === "number"
                ? s.restoreLaunchStartedAt
                : null,
            restoreLaunchCwd: normalizeNullableString(s.restoreLaunchCwd),
            lazyStart: true,
            firstMessagePreview: s.firstMessagePreview ?? null,
            terminalTitle: normalizeTerminalTitle(s.terminalTitle),
            cwd: s.cwd,
            initialCwd: s.cwd,
            status: "idle",
            needsAttention: false,
            lastExitCode: null,
            cols: 80,
            rows: 24,
          },
          sidebarWidth
        );
        shells[s.id] = {
          ...hydratedShell,
          id: s.id,
        };
        shellIds.push(s.id);
      }
      projects[p.id] = {
        id: p.id,
        name: p.name,
        path: p.path,
        expanded: true,
        shellIds,
      };
      projectOrder.push(p.id);
    }
    const active =
      (state.activeShellId && shells[state.activeShellId]?.id) ||
      projectOrder
        .map((pid) => projects[pid].shellIds[0])
        .find(Boolean) ||
      null;
    set({
      projects,
      shells,
      projectOrder,
      activeShellId: active,
      sidebarWidth,
      terminalSettings,
      hydrated: true,
    });
  },

  persist: async () => {
    const s = get();
    if (!s.hydrated) return;
    const snapshot: PersistedState = {
      projects: s.projectOrder.map((pid) => {
        const p = s.projects[pid];
        return {
          id: p.id,
          name: p.name,
          path: p.path,
          shells: p.shellIds.map((sid) => {
            const sh = s.shells[sid];
            return {
              id: sh.id,
              name: sh.name,
              autoName: sh.autoName,
              nameMode: sh.nameMode,
              agentKind: sh.agentKind,
              agentLabel: sh.agentLabel,
              restoreCapability: sh.restoreCapability,
              restoreCommandPrefix: sh.restoreCommandPrefix,
              restoreCommandSuffix: sh.restoreCommandSuffix,
              restoreFallbackCommand: sh.restoreFallbackCommand,
              newSessionCommand: sh.newSessionCommand,
              restoreTarget: sh.restoreTarget,
              restoreResolvePending: sh.restoreResolvePending,
              restoreResolveStrategy: sh.restoreResolveStrategy,
              restoreLaunchStartedAt: sh.restoreLaunchStartedAt,
              restoreLaunchCwd: sh.restoreLaunchCwd,
              firstMessagePreview: sh.firstMessagePreview,
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
    try {
      await savePersistedState(snapshot);
    } catch (e) {
      console.warn("persist failed", e);
    }
  },
}));

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

function syncShellAutoName(shell: Shell, sidebarWidth: number): Shell {
  const terminalTitle = normalizeTerminalTitle(shell.terminalTitle);
  const fallbackName = shell.autoName ?? shell.name;
  const autoName =
    terminalTitle
      ? terminalTitle
      : buildAgentShellName(
          shell.agentLabel,
          shell.firstMessagePreview,
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
    a.firstMessagePreview === b.firstMessagePreview &&
    a.terminalTitle === b.terminalTitle
  );
}

function areShellRestoreFieldsEqual(a: Shell, b: Shell): boolean {
  return (
    a.agentKind === b.agentKind &&
    a.restoreCapability === b.restoreCapability &&
    a.restoreCommandPrefix === b.restoreCommandPrefix &&
    a.restoreCommandSuffix === b.restoreCommandSuffix &&
    a.restoreFallbackCommand === b.restoreFallbackCommand &&
    a.newSessionCommand === b.newSessionCommand &&
    a.restorePending === b.restorePending &&
    a.restoreResolvePending === b.restoreResolvePending &&
    a.restoreResolveStrategy === b.restoreResolveStrategy &&
    a.restoreLaunchStartedAt === b.restoreLaunchStartedAt &&
    a.restoreLaunchCwd === b.restoreLaunchCwd &&
    areRestoreTargetsEqual(a.restoreTarget, b.restoreTarget)
  );
}

function areRestoreTargetsEqual(
  a: RestoreTarget | null,
  b: RestoreTarget | null
): boolean {
  return a?.kind === b?.kind && a?.value === b?.value;
}

function normalizeTerminalTitle(title: string | null | undefined): string | null {
  const normalized = title?.trim() ?? "";
  return normalized || null;
}

function normalizeNullableString(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function normalizeRestoreTarget(
  target: RestoreTarget | PersistedRestoreTarget | null | undefined
): RestoreTarget | null {
  const value = normalizeNullableString(target?.value);
  if (!target || !value) return null;
  if (target.kind !== "thread_id" && target.kind !== "session_id") return null;
  return {
    kind: target.kind,
    value,
  };
}

function normalizeAgentKind(value: string | null | undefined): AgentKind | null {
  if (
    value === "codex" ||
    value === "claude" ||
    value === "gemini" ||
    value === "opencode"
  ) {
    return value;
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

function normalizeRestoreCapability(
  value: string | null | undefined
): RestoreCapability | null {
  if (
    value === "exact" ||
    value === "recent" ||
    value === "best_effort" ||
    value === "unsupported"
  ) {
    return value;
  }
  return null;
}

function normalizeRestoreResolveStrategy(
  value: string | null | undefined
): RestoreResolveStrategy | null {
  if (value === "codex_new_thread" || value === "codex_latest_cwd") {
    return value;
  }
  return null;
}

function inferRestoreCapability(
  agentKind: AgentKind | null,
  restoreTarget: RestoreTarget | null,
  restoreFallbackCommand: string | null
): RestoreCapability | null {
  if (agentKind === "codex" && restoreTarget) return "exact";
  if (agentKind === "codex" && restoreFallbackCommand) return "exact";
  if (agentKind && restoreFallbackCommand) return "recent";
  return null;
}
