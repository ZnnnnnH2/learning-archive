import { getCurrentWindow } from "@tauri-apps/api/window";
import { playAlertSound } from "./alertSound";
import {
  closeDesktopNotification,
  sendDesktopNotification,
} from "./desktopNotifications";
import type { ParsedTerminalNotification } from "./shellSignals";
import { useShellAlertStore } from "./shellAlertStore";
import { useAppStore } from "./store";

const ALERT_SOUND_THROTTLE_MS = 800;
const lastAlertSoundAt = new Map<string, number>();

function getShellAlertTag(shellId: string): string {
  return `sideshell-shell-${shellId}`;
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

  const projectName = state.projects[shell.projectId]?.name ?? "Project";
  const shellName = shell.name ?? "Shell";
  return {
    title: notification.title?.trim() || `${projectName} · ${shellName}`,
    body:
      notification.body?.trim() ||
      `${shellName} in ${projectName} needs attention.`,
  };
}

export function dismissShellAlert(shellId: string) {
  useShellAlertStore.getState().dismissAlert(shellId);
  closeDesktopNotification(getShellAlertTag(shellId));
}

export async function activateShellFromAlert(shellId: string): Promise<void> {
  const state = useAppStore.getState();
  if (!state.shells[shellId]) {
    dismissShellAlert(shellId);
    return;
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
    onClick: () => activateShellFromAlert(shellId),
  });
}
