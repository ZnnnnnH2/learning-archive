import { create } from "zustand";

export interface ShellAlertToast {
  shellId: string;
  title: string;
  body: string;
  updatedAt: number;
}

interface ShowShellAlertInput {
  shellId: string;
  title: string;
  body: string;
  durationMs: number;
}

interface ShellAlertState {
  alerts: ShellAlertToast[];
  showAlert: (input: ShowShellAlertInput) => void;
  dismissAlert: (shellId: string) => void;
}

const alertTimers = new Map<string, number>();

function clearAlertTimer(shellId: string) {
  const timeoutId = alertTimers.get(shellId);
  if (timeoutId == null) {
    return;
  }
  window.clearTimeout(timeoutId);
  alertTimers.delete(shellId);
}

export const useShellAlertStore = create<ShellAlertState>((set, get) => ({
  alerts: [],

  showAlert: ({ shellId, title, body, durationMs }) => {
    clearAlertTimer(shellId);

    const updatedAt = Date.now();
    set((state) => ({
      alerts: [
        { shellId, title, body, updatedAt },
        ...state.alerts.filter((alert) => alert.shellId !== shellId),
      ],
    }));

    const timeoutId = window.setTimeout(() => {
      alertTimers.delete(shellId);
      get().dismissAlert(shellId);
    }, durationMs);
    alertTimers.set(shellId, timeoutId);
  },

  dismissAlert: (shellId) => {
    clearAlertTimer(shellId);
    set((state) => {
      if (!state.alerts.some((alert) => alert.shellId === shellId)) {
        return {};
      }
      return {
        alerts: state.alerts.filter((alert) => alert.shellId !== shellId),
      };
    });
  },
}));
