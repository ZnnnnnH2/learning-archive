import type { ShellStatus } from "./types";

const AGENT_TITLE_RE = /\b(claude|opencode)\b/i;
const TITLE_WAITING_PATTERNS = [
  /\bwaiting for input\b/i,
  /\bneeds approval\b/i,
  /\bapproval required\b/i,
  /\bneeds attention\b/i,
  /\bconfirm(?:ation)? required\b/i,
  /\binput required\b/i,
  /\bpress enter to continue\b/i,
];
const TITLE_RUNNING_PATTERNS = [
  /^\s*[|/\\-]\s+/,
  /^\s*[⠁-⣿]\s+/u,
  /\brunning\b/i,
  /\bthinking\b/i,
  /\bworking\b/i,
  /\bexecuting\b/i,
  /\bloading\b/i,
];
const TITLE_ERROR_PATTERNS = [/\berror\b/i, /\bfailed\b/i];
const TITLE_IDLE_PATTERNS = [
  /\bdone\b/i,
  /\bcompleted\b/i,
  /\bfinished\b/i,
];

export interface ParsedTerminalNotification {
  kind: "bell" | "osc9" | "osc777";
  title?: string;
  body?: string;
}

function normalizeNotificationText(value: string | null | undefined): string | undefined {
  const normalized = value?.replace(/\s+/g, " ").trim() ?? "";
  return normalized || undefined;
}

export function createBellNotification(): ParsedTerminalNotification {
  return { kind: "bell" };
}

export function parseOsc9Notification(
  payload: string
): ParsedTerminalNotification {
  return {
    kind: "osc9",
    body: normalizeNotificationText(payload),
  };
}

export function parseOsc777Notification(
  payload: string
): ParsedTerminalNotification | null {
  const [command, rawTitle, ...bodyParts] = payload.split(";");
  if ((command ?? "").trim().toLowerCase() !== "notify") {
    return null;
  }

  return {
    kind: "osc777",
    title: normalizeNotificationText(rawTitle),
    body: normalizeNotificationText(bodyParts.join(";")),
  };
}

export function detectShellStatusFromOsc133(
  payload: string,
  currentStatus: ShellStatus
): ShellStatus | null {
  const [command, ...rest] = payload
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);

  switch ((command ?? "").toUpperCase()) {
    case "A":
    case "B":
      return currentStatus === "exited" ? null : "idle";
    case "C":
      return "running";
    case "D": {
      const exitCode = Number.parseInt(rest[0] ?? "", 10);
      if (Number.isNaN(exitCode) || exitCode === 0) return "idle";
      return "error";
    }
    default:
      return null;
  }
}

export function detectShellStatusFromTitle(title: string): ShellStatus | null {
  const normalized = title.trim();
  if (!normalized) return null;

  if (
    normalized.includes("🔔") ||
    normalized.includes("❓") ||
    TITLE_WAITING_PATTERNS.some((pattern) => pattern.test(normalized))
  ) {
    return "waiting";
  }

  if (
    normalized.includes("✖") ||
    normalized.includes("❌") ||
    TITLE_ERROR_PATTERNS.some((pattern) => pattern.test(normalized))
  ) {
    return "error";
  }

  if (
    normalized.includes("✓") ||
    normalized.includes("✔") ||
    TITLE_IDLE_PATTERNS.some((pattern) => pattern.test(normalized))
  ) {
    return "idle";
  }

  if (
    normalized.includes("⏳") ||
    normalized.includes("⌛") ||
    TITLE_RUNNING_PATTERNS.some((pattern) => pattern.test(normalized))
  ) {
    return "running";
  }

  if (AGENT_TITLE_RE.test(normalized)) {
    return "idle";
  }

  return null;
}
