import type {
  AgentKind,
  RestoreCapability,
  RestoreResolveStrategy,
  RestoreTarget,
  ShellNameMode,
} from "./types";
import { basename } from "./utils";

const DEFAULT_SHELL_NAME_RE = /^Shell \d+$/i;
const DEFAULT_SIDEBAR_WIDTH = 268;
const SIDEBAR_GUTTER_PX = 96;
const ASCII_CHAR_PX = 7;
const MIN_NAME_WIDTH = 14;
const NAME_SEPARATOR = "|";

export interface DetectedAgentLaunch {
  kind: AgentKind;
  label: string;
  restoreCapability: RestoreCapability;
  restoreCommandPrefix: string | null;
  restoreCommandSuffix: string | null;
  restoreFallbackCommand: string | null;
  explicitRestoreTarget: RestoreTarget | null;
  resolveStrategy: RestoreResolveStrategy | null;
  launchCwd: string | null;
}

type CommandToken = {
  raw: string;
  value: string;
};

type AgentLaunchSpec = {
  kind: AgentKind;
  label: string;
  restoreCapability: RestoreCapability;
  resumeArgs: readonly string[];
};

type ExactRestoreTemplate = {
  prefix: string | null;
  suffix: string | null;
};

type CodexLaunchPlan = {
  restoreCapability: RestoreCapability;
  restoreCommandPrefix: string | null;
  restoreCommandSuffix: string | null;
  restoreFallbackCommand: string | null;
  explicitRestoreTarget: RestoreTarget | null;
  resolveStrategy: RestoreResolveStrategy | null;
  launchCwd: string | null;
};

const CODEX_SUBCOMMANDS = new Set([
  "exec",
  "e",
  "review",
  "login",
  "logout",
  "mcp",
  "plugin",
  "mcpserver",
  "appserver",
  "completion",
  "sandbox",
  "debug",
  "execpolicy",
  "apply",
  "a",
  "resume",
  "fork",
  "cloud",
  "cloud-tasks",
  "responsesapiproxy",
  "responses",
  "stdio-to-uds",
  "execserver",
  "features",
]);

const CODEX_NON_RESUMABLE_SUBCOMMANDS = new Set([
  "exec",
  "e",
  "review",
  "login",
  "logout",
  "mcp",
  "plugin",
  "mcpserver",
  "appserver",
  "completion",
  "sandbox",
  "debug",
  "execpolicy",
  "apply",
  "a",
  "cloud",
  "cloud-tasks",
  "responsesapiproxy",
  "responses",
  "stdio-to-uds",
  "execserver",
  "features",
]);

const CODEX_VALUE_OPTIONS = new Set([
  "-i",
  "--image",
  "-m",
  "--model",
  "--local-provider",
  "-p",
  "--profile",
  "-s",
  "--sandbox",
  "-a",
  "--ask-for-approval",
  "-C",
  "--cd",
  "--add-dir",
  "-c",
  "--config",
  "--remote",
  "--remote-auth-token-env",
  "--enable",
  "--disable",
]);

const CODEX_DROPPED_OPTIONS = new Set(["-i", "--image"]);
const CODEX_FORK_SELECTION_OPTIONS = new Set(["--last", "--all"]);
const CODEX_RESUME_SELECTION_OPTIONS = new Set([
  "--last",
  "--all",
  "--include-non-interactive",
]);

const AGENT_LAUNCH_SPECS = new Map<string, AgentLaunchSpec>([
  [
    "codex",
    {
      kind: "codex",
      label: "Codex",
      restoreCapability: "exact",
      resumeArgs: [],
    },
  ],
  [
    "claude",
    {
      kind: "claude",
      label: "Claude",
      restoreCapability: "recent",
      resumeArgs: ["--continue"],
    },
  ],
  [
    "claude-code",
    {
      kind: "claude",
      label: "Claude",
      restoreCapability: "recent",
      resumeArgs: ["--continue"],
    },
  ],
  [
    "gemini",
    {
      kind: "gemini",
      label: "Gemini",
      restoreCapability: "recent",
      resumeArgs: ["-r", "latest"],
    },
  ],
  [
    "gemini-cli",
    {
      kind: "gemini",
      label: "Gemini",
      restoreCapability: "recent",
      resumeArgs: ["-r", "latest"],
    },
  ],
  [
    "opencode",
    {
      kind: "opencode",
      label: "OpenCode",
      restoreCapability: "recent",
      resumeArgs: ["--continue"],
    },
  ],
]);

const WRAPPER_SEQUENCES = [
  ["npx"],
  ["pnpx"],
  ["bunx"],
  ["uvx"],
  ["npm", "exec"],
  ["pnpm", "dlx"],
  ["pnpm", "exec"],
  ["yarn", "dlx"],
  ["yarn", "exec"],
  ["uv", "tool", "run"],
];

export function buildDefaultShellName(index: number): string {
  return `Shell ${index}`;
}

export function isDefaultShellName(name: string): boolean {
  return DEFAULT_SHELL_NAME_RE.test(name.trim());
}

export function inferShellNameMode(name: string): ShellNameMode {
  return isDefaultShellName(name) ? "auto" : "manual";
}

export function normalizeShellNameMode(
  nameMode: string | null | undefined,
  fallbackName: string
): ShellNameMode {
  if (nameMode === "auto" || nameMode === "manual") {
    return nameMode;
  }
  return inferShellNameMode(fallbackName);
}

export function detectAgentLaunchFromCommand(
  line: string,
  currentCwd?: string | null
): DetectedAgentLaunch | null {
  const tokens = tokenizeCommandTokens(line);
  if (tokens.length === 0) return null;

  const direct = agentLaunchForToken(tokens[0].value);
  if (direct) {
    return buildDetectedAgentLaunchFromIndex(tokens, 0, currentCwd ?? null);
  }

  const normalized = normalizeCommandToken(tokens[0].value);
  for (const sequence of WRAPPER_SEQUENCES) {
    if (!matchesSequence(tokens, sequence)) continue;
    const targetIndex = firstNonFlagTokenIndex(tokens, sequence.length);
    return buildDetectedAgentLaunchFromIndex(tokens, targetIndex, currentCwd ?? null);
  }

  if (
    normalized === "cmd" ||
    normalized === "powershell" ||
    normalized === "pwsh"
  ) {
    const targetIndex = commandAfterExecutionFlagIndex(tokens);
    return buildDetectedAgentLaunchFromIndex(tokens, targetIndex, currentCwd ?? null);
  }

  return null;
}

export function detectAutoNameFromCommand(
  line: string,
  currentCwd?: string | null
): string | null {
  return detectAgentLaunchFromCommand(line, currentCwd)?.label ?? null;
}

export function buildAgentRestoreCommand(options: {
  kind: AgentKind | null;
  restoreCommandPrefix: string | null;
  restoreCommandSuffix: string | null;
  restoreFallbackCommand: string | null;
  restoreTarget: RestoreTarget | null;
}): string | null {
  const {
    kind,
    restoreCommandPrefix,
    restoreCommandSuffix,
    restoreFallbackCommand,
    restoreTarget,
  } = options;
  if (kind === "codex" && restoreTarget && restoreCommandPrefix) {
    const target = restoreTarget.value.trim();
    if (!target) return restoreFallbackCommand;
    const targetSegment = target.startsWith("-") ? `-- ${target}` : target;
    return joinCommandParts([
      restoreCommandPrefix,
      targetSegment,
      restoreCommandSuffix,
    ]);
  }
  return restoreFallbackCommand;
}

export function buildAgentShellName(
  agentLabel: string | null,
  firstMessagePreview: string | null,
  fallbackName: string,
  sidebarWidth = DEFAULT_SIDEBAR_WIDTH
): string {
  if (!agentLabel) return fallbackName;

  const cleanAgentLabel = agentLabel.trim();
  if (!cleanAgentLabel) return fallbackName;

  const cleanPreview = normalizeFirstMessagePreview(firstMessagePreview);
  if (!cleanPreview) return cleanAgentLabel;

  const totalBudget = getShellNameBudget(sidebarWidth);
  const previewBudget =
    totalBudget -
    measureDisplayWidth(cleanAgentLabel) -
    measureDisplayWidth(NAME_SEPARATOR);

  if (previewBudget <= 0) return cleanAgentLabel;

  return `${cleanAgentLabel}${NAME_SEPARATOR}${truncateDisplayWidth(
    cleanPreview,
    previewBudget
  )}`;
}

export function normalizeFirstMessagePreview(
  message: string | null | undefined
): string | null {
  const normalized = (message ?? "").replace(/\s+/g, " ").trim();
  return normalized || null;
}

export function consumeTypedInputBuffer(
  line: string,
  data: string
): { line: string; submittedLines: string[] } {
  const clean = stripInputEscapeSequences(data);
  let nextLine = line;
  const submittedLines: string[] = [];

  for (const char of clean) {
    if (char === "\r" || char === "\n") {
      const submitted = nextLine.trim();
      if (submitted) submittedLines.push(submitted);
      nextLine = "";
      continue;
    }

    if (char === "\u0003" || char === "\u0015" || char === "\u0018") {
      nextLine = "";
      continue;
    }

    if (char === "\u0008" || char === "\u007f") {
      nextLine = nextLine.slice(0, -1);
      continue;
    }

    if (char === "\t") {
      nextLine += " ";
      continue;
    }

    if (isPrintableChar(char)) {
      nextLine += char;
    }
  }

  return { line: nextLine, submittedLines };
}

function tokenizeCommandTokens(line: string): CommandToken[] {
  const tokens = line.match(/"[^"]*"|'[^']*'|`[^`]*`|[^\s]+/g) ?? [];
  return tokens.map((raw) => ({
    raw,
    value: raw.replace(/^['"`]|['"`]$/g, ""),
  }));
}

function matchesSequence(tokens: CommandToken[], sequence: string[]): boolean {
  if (tokens.length < sequence.length) return false;
  return sequence.every(
    (part, index) => normalizeCommandToken(tokens[index].value) === part
  );
}

function firstNonFlagTokenIndex(
  tokens: CommandToken[],
  start: number
): number | null {
  let positional = false;

  for (let index = start; index < tokens.length; index += 1) {
    const token = tokens[index]?.value;
    if (!token) continue;
    if (positional) return index;
    if (token === "--") {
      positional = true;
      continue;
    }
    if (token.startsWith("-")) continue;
    return index;
  }

  return null;
}

function commandAfterExecutionFlagIndex(tokens: CommandToken[]): number | null {
  for (let index = 1; index < tokens.length - 1; index += 1) {
    const token = normalizeCommandToken(tokens[index].value);
    if (token === "-c" || token === "/c" || token === "-command") {
      return firstNonFlagTokenIndex(tokens, index + 1);
    }
  }
  return null;
}

function buildDetectedAgentLaunchFromIndex(
  tokens: CommandToken[],
  targetIndex: number | null,
  currentCwd: string | null
): DetectedAgentLaunch | null {
  if (targetIndex == null) return null;
  const launch = agentLaunchForToken(tokens[targetIndex]?.value);
  if (!launch) return null;

  if (launch.kind === "codex") {
    return buildDetectedCodexLaunch(tokens, targetIndex, currentCwd);
  }
  return buildDetectedGenericAgentLaunch(tokens, targetIndex, launch);
}

function buildDetectedGenericAgentLaunch(
  tokens: CommandToken[],
  targetIndex: number,
  launch: AgentLaunchSpec
): DetectedAgentLaunch | null {
  const commandPrefix = tokens
    .slice(0, targetIndex + 1)
    .map((token) => token.raw);
  const launchArgs = stripResumeArgs(
    tokens.slice(targetIndex + 1).map((token) => token.raw),
    launch.resumeArgs
  );
  const restoreFallbackCommand = joinCommandTokens([
    ...commandPrefix,
    ...launchArgs,
    ...launch.resumeArgs,
  ]);

  return {
    kind: launch.kind,
    label: launch.label,
    restoreCapability: launch.restoreCapability,
    restoreCommandPrefix: null,
    restoreCommandSuffix: null,
    restoreFallbackCommand,
    explicitRestoreTarget: null,
    resolveStrategy: null,
    launchCwd: null,
  };
}

function buildDetectedCodexLaunch(
  tokens: CommandToken[],
  targetIndex: number,
  currentCwd: string | null
): DetectedAgentLaunch | null {
  const commandPrefixTokens = tokens
    .slice(0, targetIndex + 1)
    .map((token) => token.raw);
  const launchArgs = tokens.slice(targetIndex + 1);
  const plan = analyzeCodexLaunch(launchArgs, currentCwd);
  if (!plan) return null;

  const template = buildExactRestoreTemplate(
    commandPrefixTokens,
    plan.restoreCommandPrefix,
    plan.restoreCommandSuffix
  );
  return {
    kind: "codex",
    label: "Codex",
    restoreCapability: plan.restoreCapability,
    restoreCommandPrefix: template.prefix,
    restoreCommandSuffix: template.suffix,
    restoreFallbackCommand: prefixCodexCommand(
      commandPrefixTokens,
      plan.restoreFallbackCommand
    ),
    explicitRestoreTarget: plan.explicitRestoreTarget,
    resolveStrategy: plan.resolveStrategy,
    launchCwd: plan.launchCwd,
  };
}

function analyzeCodexLaunch(
  launchArgs: CommandToken[],
  currentCwd: string | null
): CodexLaunchPlan | null {
  const firstPositional = firstNonFlagTokenIndex(launchArgs, 0);
  if (firstPositional == null) {
    return buildCodexNewThreadPlan(
      collectCodexOptionsUntilPositional(launchArgs),
      resolveLaunchCwd(extractCodexCwd(launchArgs), currentCwd)
    );
  }

  const subcommand = normalizeCommandToken(launchArgs[firstPositional]?.value ?? "");
  if (!CODEX_SUBCOMMANDS.has(subcommand)) {
    return buildCodexNewThreadPlan(
      collectCodexOptionsUntilPositional(launchArgs),
      resolveLaunchCwd(
        extractCodexCwd(launchArgs.slice(0, firstPositional)),
        currentCwd
      )
    );
  }

  if (CODEX_NON_RESUMABLE_SUBCOMMANDS.has(subcommand)) {
    return null;
  }

  const globalOptionTokens = launchArgs.slice(0, firstPositional);
  const globalOptions = collectCodexOptionsUntilPositional(globalOptionTokens);
  const subcommandArgs = launchArgs.slice(firstPositional + 1);
  const launchCwd = resolveLaunchCwd(
    extractCodexCwd([...globalOptionTokens, ...subcommandArgs]),
    currentCwd
  );

  if (subcommand === "resume") {
    return buildCodexResumePlan(globalOptions, subcommandArgs, launchCwd);
  }

  if (subcommand === "fork") {
    return buildCodexForkPlan(globalOptions, subcommandArgs, launchCwd);
  }

  return null;
}

function buildCodexNewThreadPlan(
  globalOptions: string[],
  launchCwd: string | null
): CodexLaunchPlan {
  return {
    restoreCapability: "exact",
    restoreCommandPrefix: joinCommandTokens([...globalOptions, "resume"]),
    restoreCommandSuffix: null,
    restoreFallbackCommand: joinCommandTokens([
      ...globalOptions,
      "resume",
      "--last",
    ]),
    explicitRestoreTarget: null,
    resolveStrategy: "codex_new_thread",
    launchCwd,
  };
}

function buildCodexResumePlan(
  globalOptions: string[],
  subcommandArgs: CommandToken[],
  launchCwd: string | null
): CodexLaunchPlan | null {
  const analysis = analyzeCodexResumeInvocation(subcommandArgs);
  if (analysis.explicitRestoreTarget) {
    return {
      restoreCapability: "exact",
      restoreCommandPrefix: joinCommandTokens([...globalOptions, "resume"]),
      restoreCommandSuffix: joinCommandTokens(analysis.runtimeOptions),
      restoreFallbackCommand: joinCommandTokens([
        ...globalOptions,
        "resume",
        analysis.explicitRestoreTarget.value,
        ...analysis.runtimeOptions,
      ]),
      explicitRestoreTarget: analysis.explicitRestoreTarget,
      resolveStrategy: null,
      launchCwd,
    };
  }

  if (!analysis.hasLast) {
    return null;
  }

  return {
    restoreCapability: "exact",
    restoreCommandPrefix: joinCommandTokens([...globalOptions, "resume"]),
    restoreCommandSuffix: joinCommandTokens(analysis.runtimeOptions),
    restoreFallbackCommand: joinCommandTokens([
      ...globalOptions,
      "resume",
      "--last",
      ...analysis.runtimeOptions,
    ]),
    explicitRestoreTarget: null,
    resolveStrategy: "codex_latest_cwd",
    launchCwd,
  };
}

function buildCodexForkPlan(
  globalOptions: string[],
  subcommandArgs: CommandToken[],
  launchCwd: string | null
): CodexLaunchPlan {
  const runtimeOptions = collectCodexForkRuntimeOptions(subcommandArgs);
  return {
    restoreCapability: "exact",
    restoreCommandPrefix: joinCommandTokens([...globalOptions, "resume"]),
    restoreCommandSuffix: joinCommandTokens(runtimeOptions),
    restoreFallbackCommand: joinCommandTokens([
      ...globalOptions,
      "resume",
      "--last",
      ...runtimeOptions,
    ]),
    explicitRestoreTarget: null,
    resolveStrategy: "codex_new_thread",
    launchCwd,
  };
}

function analyzeCodexResumeInvocation(subcommandArgs: CommandToken[]): {
  explicitRestoreTarget: RestoreTarget | null;
  hasLast: boolean;
  runtimeOptions: string[];
} {
  const runtimeOptions: string[] = [];
  let pendingValueOption: string | null = null;
  let explicitRestoreTarget: RestoreTarget | null = null;
  let waitingForDoubleDashTarget = false;
  let targetCaptured = false;
  let hasLast = false;

  for (const token of subcommandArgs) {
    if (pendingValueOption) {
      if (!CODEX_DROPPED_OPTIONS.has(pendingValueOption)) {
        runtimeOptions.push(token.raw);
      }
      pendingValueOption = null;
      continue;
    }

    if (waitingForDoubleDashTarget) {
      explicitRestoreTarget = {
        kind: "thread_id",
        value: token.value,
      };
      targetCaptured = true;
      waitingForDoubleDashTarget = false;
      continue;
    }

    if (!targetCaptured && token.value === "--") {
      waitingForDoubleDashTarget = true;
      continue;
    }

    const option = codexOptionKey(token.value);
    if (option) {
      if (option === "--last") {
        hasLast = true;
        continue;
      }
      if (CODEX_RESUME_SELECTION_OPTIONS.has(option)) {
        continue;
      }
      if (!CODEX_DROPPED_OPTIONS.has(option)) {
        runtimeOptions.push(token.raw);
      }
      if (CODEX_VALUE_OPTIONS.has(option) && !hasInlineCodexOptionValue(token.value, option)) {
        pendingValueOption = option;
      }
      continue;
    }

    if (!targetCaptured) {
      explicitRestoreTarget = {
        kind: "thread_id",
        value: token.value,
      };
      targetCaptured = true;
      continue;
    }

    break;
  }

  return {
    explicitRestoreTarget,
    hasLast,
    runtimeOptions,
  };
}

function agentLaunchForToken(token: string | null): AgentLaunchSpec | null {
  if (!token) return null;
  return AGENT_LAUNCH_SPECS.get(normalizeCommandToken(token)) ?? null;
}

function normalizeCommandToken(token: string): string {
  return basename(token)
    .toLowerCase()
    .replace(/\.(cmd|bat|exe|ps1|psm1|sh)$/i, "");
}

function collectCodexOptionsUntilPositional(tokens: CommandToken[]): string[] {
  const out: string[] = [];
  let pendingValueOption: string | null = null;

  for (const token of tokens) {
    if (pendingValueOption) {
      if (!CODEX_DROPPED_OPTIONS.has(pendingValueOption)) {
        out.push(token.raw);
      }
      pendingValueOption = null;
      continue;
    }

    const option = codexOptionKey(token.value);
    if (!option) {
      break;
    }

    if (!CODEX_DROPPED_OPTIONS.has(option)) {
      out.push(token.raw);
    }

    if (CODEX_VALUE_OPTIONS.has(option) && !hasInlineCodexOptionValue(token.value, option)) {
      pendingValueOption = option;
    }
  }

  return out;
}

function collectCodexForkRuntimeOptions(tokens: CommandToken[]): string[] {
  const out: string[] = [];
  let pendingValueOption: string | null = null;
  let forkSourceCaptured = false;
  let waitingForDoubleDashSource = false;

  for (const token of tokens) {
    if (pendingValueOption) {
      if (!CODEX_DROPPED_OPTIONS.has(pendingValueOption)) {
        out.push(token.raw);
      }
      pendingValueOption = null;
      continue;
    }

    if (waitingForDoubleDashSource) {
      forkSourceCaptured = true;
      waitingForDoubleDashSource = false;
      continue;
    }

    if (!forkSourceCaptured && token.value === "--") {
      waitingForDoubleDashSource = true;
      continue;
    }

    const option = codexOptionKey(token.value);
    if (option) {
      if (CODEX_FORK_SELECTION_OPTIONS.has(option)) {
        continue;
      }
      if (!CODEX_DROPPED_OPTIONS.has(option)) {
        out.push(token.raw);
      }
      if (CODEX_VALUE_OPTIONS.has(option) && !hasInlineCodexOptionValue(token.value, option)) {
        pendingValueOption = option;
      }
      continue;
    }

    if (!forkSourceCaptured) {
      forkSourceCaptured = true;
      continue;
    }

    break;
  }

  return out;
}

function codexOptionKey(token: string): string | null {
  if (token === "--") return null;

  if (token.startsWith("--")) {
    const eq = token.indexOf("=");
    return eq >= 0 ? token.slice(0, eq) : token;
  }

  if (!token.startsWith("-") || token === "-") {
    return null;
  }

  if (token.length >= 2) {
    return token.slice(0, 2);
  }

  return token;
}

function hasInlineCodexOptionValue(token: string, option: string): boolean {
  if (option.startsWith("--")) {
    return token.startsWith(`${option}=`);
  }
  return token.length > option.length;
}

function extractCodexCwd(tokens: CommandToken[]): string | null {
  let pendingCwd = false;

  for (const token of tokens) {
    if (pendingCwd) {
      return normalizeLaunchCwd(token.value);
    }
    if (token.value === "-C" || token.value === "--cd") {
      pendingCwd = true;
      continue;
    }
    if (token.value.startsWith("--cd=")) {
      return normalizeLaunchCwd(token.value.slice("--cd=".length));
    }
    if (token.value.startsWith("-C") && token.value !== "-C") {
      return normalizeLaunchCwd(token.value.slice(2));
    }
  }

  return null;
}

function resolveLaunchCwd(
  launchCwd: string | null,
  currentCwd: string | null
): string | null {
  if (!launchCwd) return currentCwd ?? null;
  if (isAbsolutePath(launchCwd) || !currentCwd) {
    return normalizePathString(launchCwd);
  }

  return normalizePathString(joinRelativePath(currentCwd, launchCwd));
}

function normalizeLaunchCwd(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function isAbsolutePath(value: string): boolean {
  return (
    /^[a-zA-Z]:[\\/]/.test(value) ||
    value.startsWith("\\\\") ||
    value.startsWith("/")
  );
}

function joinRelativePath(basePath: string, relativePath: string): string {
  const separator = basePath.includes("\\") ? "\\" : "/";
  const base = basePath.replace(/[\\/]+$/, "");
  return `${base}${separator}${relativePath}`;
}

function normalizePathString(path: string): string {
  const isWindows = /^[a-zA-Z]:[\\/]/.test(path) || path.startsWith("\\\\");
  const hasLeadingSlash = !isWindows && path.startsWith("/");
  const rawSegments = path
    .replace(/[\\/]+/g, "/")
    .split("/")
    .filter((segment, index) => segment.length > 0 || index === 0);
  const normalizedSegments: string[] = [];

  for (const segment of rawSegments) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (
        normalizedSegments.length > 0 &&
        normalizedSegments[normalizedSegments.length - 1] !== ".."
      ) {
        normalizedSegments.pop();
      } else if (!hasLeadingSlash) {
        normalizedSegments.push(segment);
      }
      continue;
    }
    normalizedSegments.push(segment);
  }

  if (isWindows) {
    const prefix = normalizedSegments.shift() ?? "";
    const rest = normalizedSegments.join("\\");
    return rest ? `${prefix}\\${rest}` : prefix;
  }

  const joined = normalizedSegments.join("/");
  return hasLeadingSlash ? `/${joined}` : joined;
}

function buildExactRestoreTemplate(
  commandPrefixTokens: string[],
  restoreCommandPrefix: string | null,
  restoreCommandSuffix: string | null
): ExactRestoreTemplate {
  const prefix = prefixCodexCommand(commandPrefixTokens, restoreCommandPrefix);
  return {
    prefix,
    suffix: restoreCommandSuffix?.trim() || null,
  };
}

function prefixCodexCommand(
  commandPrefixTokens: string[],
  trailingCommand: string | null
): string | null {
  return joinCommandTokens([
    ...commandPrefixTokens,
    ...(trailingCommand ? [trailingCommand] : []),
  ]);
}

function joinCommandTokens(tokens: string[]): string | null {
  const joined = tokens.map((token) => token.trim()).filter(Boolean).join(" ");
  return joined || null;
}

function joinCommandParts(parts: Array<string | null | undefined>): string | null {
  const joined = parts.map((part) => part?.trim() ?? "").filter(Boolean).join(" ");
  return joined || null;
}

function stripResumeArgs(
  launchArgs: string[],
  resumeArgs: readonly string[]
): string[] {
  if (resumeArgs.length === 0) return launchArgs;

  const out: string[] = [];
  for (let index = 0; index < launchArgs.length; ) {
    if (matchesArgSequence(launchArgs, resumeArgs, index)) {
      index += resumeArgs.length;
      continue;
    }
    out.push(launchArgs[index]);
    index += 1;
  }
  return out;
}

function matchesArgSequence(
  tokens: string[],
  sequence: readonly string[],
  index: number
): boolean {
  if (index + sequence.length > tokens.length) return false;
  for (let offset = 0; offset < sequence.length; offset += 1) {
    if ((tokens[index + offset]?.trim() ?? "") !== sequence[offset]) {
      return false;
    }
  }
  return true;
}

function getShellNameBudget(sidebarWidth: number): number {
  return Math.max(
    MIN_NAME_WIDTH,
    Math.floor((sidebarWidth - SIDEBAR_GUTTER_PX) / ASCII_CHAR_PX)
  );
}

function truncateDisplayWidth(value: string, maxWidth: number): string {
  if (measureDisplayWidth(value) <= maxWidth) return value;

  let width = 0;
  let out = "";
  for (const char of value) {
    const charWidth = measureCharWidth(char);
    if (width + charWidth > maxWidth) break;
    out += char;
    width += charWidth;
  }
  return out.trimEnd();
}

function measureDisplayWidth(value: string): number {
  let width = 0;
  for (const char of value) {
    width += measureCharWidth(char);
  }
  return width;
}

function measureCharWidth(char: string): number {
  const codePoint = char.codePointAt(0) ?? 0;
  if (
    codePoint >= 0x1100 &&
    (codePoint <= 0x115f ||
      codePoint === 0x2329 ||
      codePoint === 0x232a ||
      (codePoint >= 0x2e80 && codePoint <= 0xa4cf && codePoint !== 0x303f) ||
      (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
      (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
      (codePoint >= 0xfe10 && codePoint <= 0xfe19) ||
      (codePoint >= 0xfe30 && codePoint <= 0xfe6f) ||
      (codePoint >= 0xff00 && codePoint <= 0xff60) ||
      (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
      (codePoint >= 0x1f300 && codePoint <= 0x1faff))
  ) {
    return 2;
  }
  return 1;
}

function stripInputEscapeSequences(data: string): string {
  return data
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "")
    .replace(/\x1bO./g, "")
    .replace(/\x1b./g, "");
}

function isPrintableChar(char: string): boolean {
  const code = char.charCodeAt(0);
  return code >= 0x20 && code !== 0x7f;
}
