import { AGENT_KINDS } from "./types";
import { normalizeShortcutKeymap } from "./shortcuts";
import type {
  AppLocale,
  LazyShellStartMode,
  PersistedRestoreDefaultsByAgent,
  PersistedTerminalSettings,
  RestoreDefaultsByAgent,
  TerminalSettings,
} from "./types";

export interface PtySpawnOptions {
  shellExecutable?: string;
  extraEnv?: Record<string, string>;
}

export interface TerminalEnvParseMessages {
  invalidLine: (line: number) => string;
  missingKey: (line: number) => string;
}

export const DEFAULT_TERMINAL_FONT_FAMILY =
  '"JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Sarasa Mono SC", "Maple Mono NF CN", Menlo, Consolas, monospace';
export const DEFAULT_ALERT_POPUP_DURATION_SECONDS = 3;
export const DEFAULT_LOCALE: AppLocale = detectPreferredLocale();

const DEFAULT_ENV_PARSE_MESSAGES: TerminalEnvParseMessages = {
  invalidLine: (line) =>
    `Invalid environment variable on line ${line}. Use KEY=VALUE.`,
  missingKey: (line) =>
    `Invalid environment variable on line ${line}. Missing key.`,
};

export const DEFAULT_TERMINAL_SETTINGS: TerminalSettings = {
  locale: DEFAULT_LOCALE,
  shellExecutable: "",
  fontFamily: DEFAULT_TERMINAL_FONT_FAMILY,
  extraEnvText: "",
  alertPopupDurationSeconds: DEFAULT_ALERT_POPUP_DURATION_SECONDS,
  codexUseSelfSummaryTitle: false,
  restoreDefaultsByAgent: {},
  shortcutKeymap: normalizeShortcutKeymap(),
};

export function normalizeTerminalSettings(
  input?: PersistedTerminalSettings | null
): TerminalSettings {
  const shellExecutable = (input?.shellExecutable ?? "").trim();
  const fontFamily = (input?.fontFamily ?? "").trim();
  return {
    locale: normalizeAppLocale(input?.locale),
    shellExecutable,
    fontFamily: fontFamily || DEFAULT_TERMINAL_FONT_FAMILY,
    extraEnvText: normalizeLineEndings(input?.extraEnvText ?? "").trim(),
    alertPopupDurationSeconds: normalizeAlertPopupDurationSeconds(
      input?.alertPopupDurationSeconds
    ),
    codexUseSelfSummaryTitle: Boolean(input?.codexUseSelfSummaryTitle),
    restoreDefaultsByAgent: normalizeRestoreDefaultsByAgent(
      input?.restoreDefaultsByAgent
    ),
    shortcutKeymap: normalizeShortcutKeymap(input?.shortcutKeymap),
  };
}

export function normalizeRestoreDefaultsByAgent(
  input?: PersistedRestoreDefaultsByAgent | null
): RestoreDefaultsByAgent {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }

  const normalized: RestoreDefaultsByAgent = {};
  for (const agentKind of AGENT_KINDS) {
    const mode = normalizeLazyShellStartMode(input[agentKind]);
    if (mode) {
      normalized[agentKind] = mode;
    }
  }
  return normalized;
}

export function parseTerminalEnvText(
  value: string,
  messages: TerminalEnvParseMessages = DEFAULT_ENV_PARSE_MESSAGES
): Record<string, string> {
  const env: Record<string, string> = {};
  const lines = normalizeLineEndings(value).split("\n");

  for (const [index, rawLine] of lines.entries()) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const eq = line.indexOf("=");
    if (eq <= 0) {
      throw new Error(messages.invalidLine(index + 1));
    }

    const key = line.slice(0, eq).trim();
    if (!key) {
      throw new Error(messages.missingKey(index + 1));
    }

    env[key] = line.slice(eq + 1);
  }

  return env;
}

export function buildPtySpawnOptions(
  settings: TerminalSettings
): PtySpawnOptions {
  const shellExecutable = settings.shellExecutable.trim();
  const extraEnv = parseTerminalEnvText(settings.extraEnvText);

  return {
    shellExecutable: shellExecutable || undefined,
    extraEnv: Object.keys(extraEnv).length > 0 ? extraEnv : undefined,
  };
}

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n?/g, "\n");
}

function detectPreferredLocale(): AppLocale {
  if (typeof navigator === "undefined") {
    return "en";
  }

  const languages = navigator.languages?.length
    ? navigator.languages
    : [navigator.language];

  return languages.some((language) => /^zh\b/i.test(language))
    ? "zh-CN"
    : "en";
}

function normalizeAlertPopupDurationSeconds(
  value: number | null | undefined
): number {
  if (!Number.isFinite(value) || value == null || value <= 0) {
    return DEFAULT_ALERT_POPUP_DURATION_SECONDS;
  }
  return Math.max(1, Math.round(value));
}

function normalizeAppLocale(value: string | null | undefined): AppLocale {
  if (value === "zh-CN") {
    return value;
  }
  if (value === "en") {
    return value;
  }
  return DEFAULT_LOCALE;
}

function normalizeLazyShellStartMode(
  value: string | null | undefined
): LazyShellStartMode | null {
  if (
    value === "restore" ||
    value === "new_agent_session" ||
    value === "terminal"
  ) {
    return value;
  }
  return null;
}
