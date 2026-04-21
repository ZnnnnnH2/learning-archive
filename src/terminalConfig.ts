import type {
  PersistedTerminalSettings,
  TerminalSettings,
} from "./types";

export interface PtySpawnOptions {
  shellExecutable?: string;
  extraEnv?: Record<string, string>;
}

export const DEFAULT_TERMINAL_FONT_FAMILY =
  '"JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Sarasa Mono SC", "Maple Mono NF CN", Menlo, Consolas, monospace';
export const DEFAULT_ALERT_POPUP_DURATION_SECONDS = 3;

export const DEFAULT_TERMINAL_SETTINGS: TerminalSettings = {
  shellExecutable: "",
  fontFamily: DEFAULT_TERMINAL_FONT_FAMILY,
  extraEnvText: "",
  alertPopupDurationSeconds: DEFAULT_ALERT_POPUP_DURATION_SECONDS,
};

export function normalizeTerminalSettings(
  input?: PersistedTerminalSettings | null
): TerminalSettings {
  const shellExecutable = (input?.shellExecutable ?? "").trim();
  const fontFamily = (input?.fontFamily ?? "").trim();
  return {
    shellExecutable,
    fontFamily: fontFamily || DEFAULT_TERMINAL_FONT_FAMILY,
    extraEnvText: normalizeLineEndings(input?.extraEnvText ?? "").trim(),
    alertPopupDurationSeconds: normalizeAlertPopupDurationSeconds(
      input?.alertPopupDurationSeconds
    ),
  };
}

export function parseTerminalEnvText(
  value: string
): Record<string, string> {
  const env: Record<string, string> = {};
  const lines = normalizeLineEndings(value).split("\n");

  for (const [index, rawLine] of lines.entries()) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const eq = line.indexOf("=");
    if (eq <= 0) {
      throw new Error(
        `Invalid environment variable on line ${index + 1}. Use KEY=VALUE.`
      );
    }

    const key = line.slice(0, eq).trim();
    if (!key) {
      throw new Error(
        `Invalid environment variable on line ${index + 1}. Missing key.`
      );
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

function normalizeAlertPopupDurationSeconds(
  value: number | null | undefined
): number {
  if (!Number.isFinite(value) || value == null || value <= 0) {
    return DEFAULT_ALERT_POPUP_DURATION_SECONDS;
  }
  return Math.max(1, Math.round(value));
}
