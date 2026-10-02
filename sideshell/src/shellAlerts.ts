import { getCurrentWindow } from "@tauri-apps/api/window";
import { playAlertSound } from "./alertSound";
import {
  closeDesktopNotification,
  sendDesktopNotification,
} from "./desktopNotifications";
import type { ParsedTerminalNotification } from "./shellSignals";
import { useShellAlertStore } from "./shellAlertStore";
import { useAppStore } from "./store";
import { translate } from "./i18n";

const ALERT_SOUND_THROTTLE_MS = 800;
const lastAlertSoundAt = new Map<string, number>();
export const SHELL_ALERT_TAG_PREFIX = "sideshell-shell-";

function logShellAlertDebug(message: string, data: Record<string, unknown>) {
  if (import.meta.env.DEV) {
    console.debug(`[shell-alerts] ${message}`, data);
  }
}

function getShellAlertTag(shellId: string): string {
  return `${SHELL_ALERT_TAG_PREFIX}${shellId}`;
}

export function isShellAlertTag(tag: string): boolean {
  return tag.trim().startsWith(SHELL_ALERT_TAG_PREFIX);
}

function getShellIdFromAlertTag(tag: string): string | null {
  const normalizedTag = tag.trim();
  if (!isShellAlertTag(normalizedTag)) {
    return null;
  }

  const shellId = normalizedTag.slice(SHELL_ALERT_TAG_PREFIX.length);
  return shellId || null;
}

function buildShellAlertMessage(
  shellId: string,
  notification: ParsedTerminalNotification
) {
  const state = useAppStore.getState();
  const shell = state.shells[shellId];
  if (!shell) {
    return null;
  }

  const locale = state.terminalSettings.locale;
  const projectName =
    state.projects[shell.projectId]?.name ??
    translate(locale, "alerts.defaultProject");
  const shellName =
    shell.name ?? translate(locale, "alerts.defaultShell");
  return {
    title: notification.title?.trim() || `${projectName} · ${shellName}`,
    body:
      notification.body?.trim() ||
      translate(locale, "alerts.defaultBody", { shellName, projectName }),
  };
}

export function dismissShellAlert(shellId: string) {
  useShellAlertStore.getState().dismissAlert(shellId);
  closeDesktopNotification(getShellAlertTag(shellId));
}

export async function activateShellFromAlert(shellId: string): Promise<void> {
  const state = useAppStore.getState();
  const shell = state.shells[shellId];
  if (!shell) {
    logShellAlertDebug("activation ignored for missing shell", { shellId });
    dismissShellAlert(shellId);
    return;
  }

  const project = state.projects[shell.projectId];
  if (project && !project.expanded) {
    state.toggleProjectExpand(shell.projectId);
  }

  state.setActive(shellId);
  state.setShellAttention(shellId, false);
  dismissShellAlert(shellId);

  try {
    const appWindow = getCurrentWindow();
    await appWindow.show();
    await appWindow.unminimize();
    await appWindow.setFocus();
  } catch (error) {
    console.warn("failed to focus app window from alert", error);
  }
}

export async function activateShellAlertByTag(tag: string): Promise<void> {
  const shellId = getShellIdFromAlertTag(tag);
  if (!shellId) {
    logShellAlertDebug("activation ignored for invalid tag", { tag });
    return;
  }
  await activateShellFromAlert(shellId);
}

export function raiseShellAlert(
  shellId: string,
  notification: ParsedTerminalNotification
) {
  const message = buildShellAlertMessage(shellId, notification);
  if (!message) {
    return;
  }

  const appState = useAppStore.getState();
  const durationMs = appState.terminalSettings.alertPopupDurationSeconds * 1000;
  const isActiveShell = appState.activeShellId === shellId;

  if (isActiveShell) {
    appState.setShellAttention(shellId, false);
  } else {
    appState.setShellAttention(shellId, true);
  }

  useShellAlertStore.getState().showAlert({
    shellId,
    title: message.title,
    body: message.body,
    durationMs,
  });

  const now = Date.now();
  const lastPlayedAt = lastAlertSoundAt.get(shellId) ?? 0;
  if (now - lastPlayedAt >= ALERT_SOUND_THROTTLE_MS) {
    lastAlertSoundAt.set(shellId, now);
    void playAlertSound();
  }

  void sendDesktopNotification({
    title: message.title,
    body: message.body,
    tag: getShellAlertTag(shellId),
    timeoutMs: durationMs,
  });
}
