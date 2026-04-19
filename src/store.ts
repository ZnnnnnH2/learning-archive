import { create } from "zustand";
import type {
  PersistedState,
  Project,
  Shell,
  ShellStatus,
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
  hydrated: boolean;

  addProject: (path: string, name?: string) => Project;
  removeProject: (id: string) => void;
  renameProject: (id: string, name: string) => void;
  toggleProjectExpand: (id: string) => void;
  reorderProjects: (order: string[]) => void;

  addShell: (projectId: string, opts?: { cwd?: string; name?: string }) => Shell;
  removeShell: (id: string) => void;
  renameShell: (id: string, name: string) => void;
  cloneShell: (id: string) => Shell | null;
  setShellStatus: (id: string, status: ShellStatus) => void;
  setShellUnread: (id: string, v: boolean) => void;
  setShellCwd: (id: string, cwd: string) => void;
  setShellSize: (id: string, cols: number, rows: number) => void;
  setShellSession: (id: string, sessionId: string) => void;
  setShellExit: (id: string, code: number) => void;
  reorderShells: (projectId: string, order: string[]) => void;

  setActive: (id: string | null) => void;
  setSidebarWidth: (w: number) => void;
  toggleSidebar: () => void;

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
    const shell: Shell = {
      id,
      sessionId: null,
      projectId,
      name: opts?.name ?? `Shell ${idx}`,
      cwd,
      initialCwd: cwd,
      status: "idle",
      hasUnread: false,
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
      return { shells: { ...s.shells, [id]: { ...sh, name } } };
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

  setShellUnread: (id, v) =>
    set((s) => {
      const sh = s.shells[id];
      if (!sh || sh.hasUnread === v) return {};
      return { shells: { ...s.shells, [id]: { ...sh, hasUnread: v } } };
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
      return { shells: { ...s.shells, [id]: { ...sh, sessionId } } };
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
    set({ activeShellId: id });
    if (id) {
      const sh = get().shells[id];
      if (sh?.hasUnread) {
        get().setShellUnread(id, false);
      }
    }
    get().persist();
  },

  setSidebarWidth: (w) => {
    set({ sidebarWidth: Math.max(180, Math.min(560, w)) });
    get().persist();
  },

  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  hydrateFrom: (state) => {
    const projects: Record<string, Project> = {};
    const shells: Record<string, Shell> = {};
    const projectOrder: string[] = [];
    for (const p of state.projects ?? []) {
      const shellIds: string[] = [];
      for (const s of p.shells ?? []) {
        shells[s.id] = {
          id: s.id,
          sessionId: null,
          projectId: p.id,
          name: s.name,
          cwd: s.cwd,
          initialCwd: s.cwd,
          status: "idle",
          hasUnread: false,
          lastExitCode: null,
          cols: 80,
          rows: 24,
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
      sidebarWidth: state.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH,
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
            return { id: sh.id, name: sh.name, cwd: sh.cwd || sh.initialCwd };
          }),
        };
      }),
      activeShellId: s.activeShellId,
      sidebarWidth: s.sidebarWidth,
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
