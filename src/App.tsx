import { useCallback, useEffect, useRef } from "react";
import { getCurrent, onOpenUrl } from "@tauri-apps/plugin-deep-link";
import { primeAlertSound } from "./alertSound";
import { ShellAlertsOverlay } from "./components/ShellAlertsOverlay";
import { Sidebar } from "./components/Sidebar";
import { TerminalHost } from "./components/TerminalHost";
import { loadPersistedState, onShellNotificationActivated } from "./ipc";
import { getShellAlertTagFromDeepLink } from "./notificationDeepLinks";
import { matchShortcutAction } from "./shortcuts";
import { activateShellAlertByTag } from "./shellAlerts";
import { useI18n } from "./useI18n";
import { useAppStore } from "./store";
import type { ShortcutActionId } from "./types";

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
  const shortcutKeymap = useAppStore((s) => s.terminalSettings.shortcutKeymap);
  const queueOrActivateNotificationTag = useCallback((tag: string) => {
    if (!useAppStore.getState().hydrated) {
      pendingNotificationTagsRef.current.push(tag);
      return;
    }
    void activateShellAlertByTag(tag);
  }, []);

  const queueOrActivateDeepLinkUrls = useCallback(
    (urls: string[] | null) => {
      if (!urls) {
        return;
      }

      for (const rawUrl of urls) {
        const tag = getShellAlertTagFromDeepLink(rawUrl);
        if (!tag) {
          if (import.meta.env.DEV) {
            console.debug("ignored deep link", { rawUrl });
          }
          continue;
        }
        queueOrActivateNotificationTag(tag);
      }
    },
    [queueOrActivateNotificationTag]
  );

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
      queueOrActivateNotificationTag(event.tag);
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
  }, [queueOrActivateNotificationTag]);

  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;

    getCurrent()
      .then((urls) => {
        if (!disposed) {
          queueOrActivateDeepLinkUrls(urls);
        }
      })
      .catch((error) => {
        console.warn("failed to read current deep links", error);
      });

    onOpenUrl((urls) => {
      queueOrActivateDeepLinkUrls(urls);
    })
      .then((cleanup) => {
        if (disposed) {
          cleanup();
          return;
        }
        unlisten = cleanup;
      })
      .catch((error) => {
        console.warn("failed to listen for deep links", error);
      });

    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [queueOrActivateDeepLinkUrls]);

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
      if (isEditableShortcutTarget(e.target) || isTerminalShortcutTarget(e.target)) {
        return;
      }

      const actionId = matchShortcutAction(shortcutKeymap, e, "app");
      if (!actionId) return;

      e.preventDefault();
      handleAppShortcut(actionId);
    };

    const handleAppShortcut = (actionId: ShortcutActionId) => {
      if (actionId === "app.toggleSidebar") {
        toggleSidebar();
      } else if (actionId === "app.newShell") {
        const active = useAppStore.getState().shells[activeShellId ?? ""];
        const projectId = active?.projectId ?? projectOrder[0];
        if (projectId && projects[projectId]) addShell(projectId);
      } else if (actionId === "app.cloneShell") {
        if (activeShellId) cloneShell(activeShellId);
      } else if (actionId === "app.closeShell") {
        if (activeShellId) removeShell(activeShellId);
      } else if (actionId.startsWith("app.focusShell")) {
        const shellNumber = Number(actionId.replace("app.focusShell", ""));
        focusShellByIndex(shellNumber - 1);
      }
    };

    const focusShellByIndex = (index: number) => {
      const flat: string[] = [];
      for (const projectId of projectOrder) {
        for (const shellId of projects[projectId]?.shellIds ?? []) {
          flat.push(shellId);
        }
      }
      const target = flat[index];
      if (target) {
        setActive(target);
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
    shortcutKeymap,
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

function isEditableShortcutTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return Boolean(
    target.closest(
      "input, textarea, select, [contenteditable='true'], [data-app-shortcuts='ignore']"
    )
  );
}

function isTerminalShortcutTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest(".xterm-host, .xterm"));
}
