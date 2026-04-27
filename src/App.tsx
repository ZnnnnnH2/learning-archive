import { useEffect, useRef } from "react";
import { primeAlertSound } from "./alertSound";
import { ShellAlertsOverlay } from "./components/ShellAlertsOverlay";
import { Sidebar } from "./components/Sidebar";
import { TerminalHost } from "./components/TerminalHost";
import { loadPersistedState, onShellNotificationActivated } from "./ipc";
import { activateShellAlertByTag } from "./shellAlerts";
import { useI18n } from "./useI18n";
import { useAppStore } from "./store";

export default function App() {
  const { locale, t } = useI18n();
  const pendingNotificationTagsRef = useRef<string[]>([]);
  const hydrated = useAppStore((s) => s.hydrated);
  const hydrateFrom = useAppStore((s) => s.hydrateFrom);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const activeShellId = useAppStore((s) => s.activeShellId);
  const projectOrder = useAppStore((s) => s.projectOrder);
  const projects = useAppStore((s) => s.projects);
  const addShell = useAppStore((s) => s.addShell);
  const cloneShell = useAppStore((s) => s.cloneShell);
  const removeShell = useAppStore((s) => s.removeShell);
  const setActive = useAppStore((s) => s.setActive);

  useEffect(() => {
    primeAlertSound();
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;

    onShellNotificationActivated((event) => {
      if (import.meta.env.DEV) {
        console.debug("shell notification activated", { tag: event.tag });
      }
      if (!useAppStore.getState().hydrated) {
        pendingNotificationTagsRef.current.push(event.tag);
        return;
      }
      void activateShellAlertByTag(event.tag);
    })
      .then((cleanup) => {
        if (disposed) {
          cleanup();
          return;
        }
        unlisten = cleanup;
      })
      .catch((error) => {
        console.warn("failed to listen for shell notification activation", error);
      });

    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    if (!hydrated || pendingNotificationTagsRef.current.length === 0) {
      return;
    }

    const pendingTags = pendingNotificationTagsRef.current.splice(0);
    for (const tag of pendingTags) {
      void activateShellAlertByTag(tag);
    }
  }, [hydrated]);

  useEffect(() => {
    (async () => {
      try {
        const state = await loadPersistedState();
        hydrateFrom(state);
      } catch (e) {
        console.warn("load_state failed", e);
        hydrateFrom({ projects: [] });
      }
    })();
  }, [hydrateFrom]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      if (mod && (e.key === "t" || e.key === "T")) {
        e.preventDefault();
        const active = useAppStore.getState().shells[activeShellId ?? ""];
        const pid = active?.projectId ?? projectOrder[0];
        if (pid && projects[pid]) addShell(pid);
        return;
      }
      if (mod && e.shiftKey && (e.key === "d" || e.key === "D")) {
        e.preventDefault();
        if (activeShellId) cloneShell(activeShellId);
        return;
      }
      if (mod && (e.key === "w" || e.key === "W")) {
        e.preventDefault();
        if (activeShellId) removeShell(activeShellId);
        return;
      }
      if (mod && e.key >= "1" && e.key <= "9") {
        const idx = parseInt(e.key, 10) - 1;
        const flat: string[] = [];
        for (const pid of projectOrder) {
          for (const sid of projects[pid]?.shellIds ?? []) flat.push(sid);
        }
        const target = flat[idx];
        if (target) {
          e.preventDefault();
          setActive(target);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    activeShellId,
    addShell,
    cloneShell,
    projectOrder,
    projects,
    removeShell,
    setActive,
    toggleSidebar,
  ]);

  if (!hydrated) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-bg-0 text-text-2 text-[12px]">
        <span className="anim-pulse">{t("app.loading")}</span>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex bg-bg-0 text-text-0">
      <Sidebar />
      <TerminalHost />
      <ShellAlertsOverlay />
    </div>
  );
}
