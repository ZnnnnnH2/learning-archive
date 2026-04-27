import type {
  AgentKind,
  ShellNameMode,
} from "./types";
import { basename } from "./utils";

const DEFAULT_SHELL_NAME_RE = /^Shell \d+$/i;
const DEFAULT_SIDEBAR_WIDTH = 268;
const SIDEBAR_GUTTER_PX = 96;
const ASCII_CHAR_PX = 7;
const MIN_NAME_WIDTH = 14;
const NAME_SEPARATOR = "|";
const CODEX_TITLE_SPINNER_RE = /^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*/u;

const TASK_SUMMARY_LEAD_PATTERNS = [
  /^(?:please\s+)?(?:can|could|would)\s+you\s+/i,
  /^(?:please\s+)?help\s+me\s+/i,
  /^(?:please\s+)?(?:take a look at|look at|check out)\s+/i,
  /^(?:请你|请|麻烦你|麻烦|帮我|帮忙|我想让你|我想请你|想让你|能不能|可以)\s*/u,
  /^(?:看一下|看下|看看|瞅一下|瞅瞅)\s*/u,
] as const;

const LOW_SIGNAL_TASK_SUMMARY_PATTERNS = [
  /^(?:ok(?:ay)?|yes|yeah|yep|sure|go ahead|sounds good|continue)$/i,
  /^(?:好(?:的|吧)?|行|可以|收到|是的?|对(?:的)?|嗯)$/u,
  /^(?:继续(?:吧|做|搞|处理|实现)?|开始吧|实现(?:吧)?|做吧|搞吧)$/u,
] as const;

const COMMON_SHELL_COMMANDS = new Set([
  "bash",
  "bun",
  "bunx",
  "cargo",
  "cat",
  "cd",
  "claude",
  "claude-code",
  "cmd",
  "codex",
  "dir",
  "fish",
  "gemini",
  "gemini-cli",
  "git",
  "ls",
  "mkdir",
  "node",
  "npm",
  "npx",
  "opencode",
  "pnpm",
  "pnpx",
  "powershell",
  "pwsh",
  "python",
  "python3",
  "pytest",
  "rg",
  "uv",
  "uvx",
  "yarn",
  "zsh",
]);

export interface DetectedAgentLaunch {
  kind: AgentKind;
  label: string;
  resumeEntryCommand: string | null;
  newSessionCommand: string | null;
}

type CommandToken = {
  raw: string;
  value: string;
};

type AgentLaunchSpec = {
  kind: AgentKind;
  label: string;
  resumeArgs: readonly string[];
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
      resumeArgs: [],
    },
  ],
  [
    "claude",
    {
      kind: "claude",
      label: "Claude",
      resumeArgs: ["--continue"],
    },
  ],
  [
    "claude-code",
    {
      kind: "claude",
      label: "Claude",
      resumeArgs: ["--continue"],
    },
  ],
  [
    "gemini",
    {
      kind: "gemini",
      label: "Gemini",
      resumeArgs: ["-r", "latest"],
    },
  ],
  [
    "gemini-cli",
    {
      kind: "gemini",
      label: "Gemini",
      resumeArgs: ["-r", "latest"],
    },
  ],
  [
    "opencode",
    {
      kind: "opencode",
      label: "OpenCode",
      resumeArgs: ["--continue"],
    },
  ],
]);

const DEFAULT_AGENT_NEW_SESSION_COMMANDS: Record<AgentKind, string> = {
  codex: "codex",
  claude: "claude",
  gemini: "gemini",
  opencode: "opencode",
};

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
  _currentCwd?: string | null
): DetectedAgentLaunch | null {
  const tokens = tokenizeCommandTokens(line);
  if (tokens.length === 0) return null;

  const direct = agentLaunchForToken(tokens[0].value);
  if (direct) {
    return buildDetectedAgentLaunchFromIndex(tokens, 0);
  }

  const normalized = normalizeCommandToken(tokens[0].value);
  for (const sequence of WRAPPER_SEQUENCES) {
    if (!matchesSequence(tokens, sequence)) continue;
    const targetIndex = firstNonFlagTokenIndex(tokens, sequence.length);
    return buildDetectedAgentLaunchFromIndex(tokens, targetIndex);
  }

  if (
    normalized === "cmd" ||
    normalized === "powershell" ||
    normalized === "pwsh"
  ) {
    const targetIndex = commandAfterExecutionFlagIndex(tokens);
    return buildDetectedAgentLaunchFromIndex(tokens, targetIndex);
  }

  return null;
}

export function detectAutoNameFromCommand(
  line: string,
  currentCwd?: string | null
): string | null {
  return detectAgentLaunchFromCommand(line, currentCwd)?.label ?? null;
}

export function buildDefaultAgentResumeEntryCommand(
  kind: AgentKind | null
): string | null {
  switch (kind) {
    case "codex":
      return "codex resume";
    case "claude":
      return "claude --resume";
    case "gemini":
      return "gemini --list-sessions";
    case "opencode":
      return "opencode session list";
    default:
      return null;
  }
}

export function buildDefaultAgentNewSessionCommand(
  kind: AgentKind | null
): string | null {
  return kind ? DEFAULT_AGENT_NEW_SESSION_COMMANDS[kind] : null;
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

export function summarizeAgentTaskFromInput(
  message: string | null | undefined
): string | null {
  const normalized = normalizeFirstMessagePreview(message);
  if (!normalized) return null;
  if (normalized.startsWith("/")) return null;
  if (looksLikeShellCommandMessage(normalized)) return null;

  let summary = normalized;
  for (let pass = 0; pass < TASK_SUMMARY_LEAD_PATTERNS.length; pass += 1) {
    let changed = false;
    for (const pattern of TASK_SUMMARY_LEAD_PATTERNS) {
      const next = summary.replace(pattern, "").trim();
      if (next && next !== summary) {
        summary = next;
        changed = true;
      }
    }
    if (!changed) break;
  }

  summary = summary
    .split(/[。！？!?]/, 1)[0]
    ?.replace(/^[,，:：;；\-|\s]+|[,，:：;；\-|\s]+$/g, "")
    .trim();

  if (!summary) return null;
  if (LOW_SIGNAL_TASK_SUMMARY_PATTERNS.some((pattern) => pattern.test(summary))) {
    return null;
  }

  if (!containsCjk(summary) && measureDisplayWidth(summary) < 4) {
    return null;
  }

  return summary;
}

export function buildCodexSummaryShellName(
  taskSummary: string | null | undefined,
  terminalTitle: string | null | undefined,
  sidebarWidth = DEFAULT_SIDEBAR_WIDTH
): string | null {
  const summary = normalizeFirstMessagePreview(taskSummary);
  if (!summary) return null;

  const spinner = extractCodexTitleSpinner(terminalTitle);
  const totalBudget = getShellNameBudget(sidebarWidth);
  const prefix = spinner ? `${spinner} ` : "";
  const availableBudget = Math.max(
    1,
    totalBudget - measureDisplayWidth(prefix)
  );
  const truncatedSummary = truncateDisplayWidth(summary, availableBudget);
  const combined = `${prefix}${truncatedSummary}`.trim();
  return combined || null;
}

export function extractCodexTitleSpinner(
  title: string | null | undefined
): string | null {
  const normalized = normalizeFirstMessagePreview(title);
  if (!normalized) return null;
  const match = normalized.match(CODEX_TITLE_SPINNER_RE);
  return match?.[0]?.trim() || null;
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

function looksLikeShellCommandMessage(message: string): boolean {
  if (
    message.startsWith("./") ||
    message.startsWith("../") ||
    /^[a-zA-Z]:[\\/]/.test(message)
  ) {
    return true;
  }

  const firstToken = tokenizeCommandTokens(message)[0]?.value;
  if (!firstToken) return false;
  return COMMON_SHELL_COMMANDS.has(normalizeCommandToken(firstToken));
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

function firstCodexPositionalIndex(
  tokens: CommandToken[],
  start: number
): number | null {
  let pendingValueOption: string | null = null;
  let positional = false;

  for (let index = start; index < tokens.length; index += 1) {
    const token = tokens[index];
    const value = token?.value;
    if (!value) continue;

    if (positional) return index;

    if (pendingValueOption) {
      if (isSuspiciousCodexOptionValue(pendingValueOption, value)) {
        pendingValueOption = null;
        return index;
      }
      pendingValueOption = null;
      continue;
    }

    if (value === "--") {
      positional = true;
      continue;
    }

    const option = codexOptionKey(value);
    if (option) {
      if (
        CODEX_VALUE_OPTIONS.has(option) &&
        !hasInlineCodexOptionValue(value, option)
      ) {
        pendingValueOption = option;
      }
      continue;
    }

    return index;
  }

  return null;
}

function buildDetectedAgentLaunchFromIndex(
  tokens: CommandToken[],
  targetIndex: number | null
): DetectedAgentLaunch | null {
  if (targetIndex == null) return null;
  const launch = agentLaunchForToken(tokens[targetIndex]?.value);
  if (!launch) return null;

  if (launch.kind === "codex") {
    return buildDetectedCodexLaunch(tokens, targetIndex);
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
  const launchArgs = tokens.slice(targetIndex + 1).map((token) => token.raw);

  switch (launch.kind) {
    case "claude":
      return buildDetectedClaudeLaunch(commandPrefix, launch.label, launchArgs);
    case "gemini":
      return buildDetectedGeminiLaunch(commandPrefix, launch.label, launchArgs);
    case "opencode":
      return buildDetectedOpenCodeLaunch(commandPrefix, launch.label, launchArgs);
    default:
      return null;
  }
}

function buildDetectedCodexLaunch(
  tokens: CommandToken[],
  targetIndex: number
): DetectedAgentLaunch | null {
  const commandPrefixTokens = tokens
    .slice(0, targetIndex + 1)
    .map((token) => token.raw);
  const launchArgs = tokens.slice(targetIndex + 1);
  const plan = analyzeCodexLaunch(launchArgs);
  if (!plan) return null;

  return {
    kind: "codex",
    label: "Codex",
    resumeEntryCommand: prefixCodexCommand(
      commandPrefixTokens,
      plan.resumeEntryCommand
    ),
    newSessionCommand: prefixCodexCommand(
      commandPrefixTokens,
      plan.newSessionCommand
    ),
  };
}

function analyzeCodexLaunch(launchArgs: CommandToken[]): {
  resumeEntryCommand: string | null;
  newSessionCommand: string | null;
} | null {
  const firstPositional = firstCodexPositionalIndex(launchArgs, 0);
  if (firstPositional == null) {
    return buildCodexPlanFromRuntimeOptions(
      collectCodexOptionsUntilPositional(launchArgs)
    );
  }

  const subcommand = normalizeCommandToken(launchArgs[firstPositional]?.value ?? "");
  if (!CODEX_SUBCOMMANDS.has(subcommand)) {
    return buildCodexPlanFromRuntimeOptions(
      collectCodexOptionsUntilPositional(launchArgs)
    );
  }

  if (CODEX_NON_RESUMABLE_SUBCOMMANDS.has(subcommand)) {
    return null;
  }

  const globalOptionTokens = launchArgs.slice(0, firstPositional);
  const globalOptions = collectCodexOptionsUntilPositional(globalOptionTokens);
  const subcommandArgs = launchArgs.slice(firstPositional + 1);

  if (subcommand === "resume") {
    return buildCodexPlanFromRuntimeOptions(
      mergeCodexRuntimeOptions(globalOptions, collectCodexResumeRuntimeOptions(subcommandArgs))
    );
  }

  if (subcommand === "fork") {
    return buildCodexPlanFromRuntimeOptions(
      mergeCodexRuntimeOptions(globalOptions, collectCodexForkRuntimeOptions(subcommandArgs))
    );
  }

  return null;
}

function buildCodexPlanFromRuntimeOptions(globalOptions: string[]): {
  resumeEntryCommand: string | null;
  newSessionCommand: string | null;
} {
  return {
    resumeEntryCommand: joinCommandTokens([...globalOptions, "resume"]),
    newSessionCommand: joinCommandTokens(globalOptions),
  };
}

function collectCodexResumeRuntimeOptions(subcommandArgs: CommandToken[]): string[] {
  const runtimeOptions: string[] = [];
  let pendingValueOption: string | null = null;
  let waitingForDoubleDashTarget = false;
  let targetCaptured = false;

  for (const token of subcommandArgs) {
    if (pendingValueOption) {
      if (isSuspiciousCodexOptionValue(pendingValueOption, token.value)) {
        pendingValueOption = null;
        break;
      }
      if (!CODEX_DROPPED_OPTIONS.has(pendingValueOption)) {
        runtimeOptions.push(token.raw);
      }
      pendingValueOption = null;
      continue;
    }

    if (waitingForDoubleDashTarget) {
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
      targetCaptured = true;
      continue;
    }

    break;
  }

  return runtimeOptions;
}

function buildDetectedClaudeLaunch(
  commandPrefix: string[],
  label: string,
  launchArgs: string[]
): DetectedAgentLaunch {
  const runtimeArgs = stripArgsWithOptionalValues(launchArgs, new Set([
    "-c",
    "--continue",
    "-r",
    "--resume",
    "--from-pr",
    "--session-id",
    "--fork-session",
  ]));
  return {
    kind: "claude",
    label,
    resumeEntryCommand: joinCommandTokens([
      ...commandPrefix,
      ...runtimeArgs,
      "--resume",
    ]),
    newSessionCommand: joinCommandTokens([...commandPrefix, ...runtimeArgs]),
  };
}

function buildDetectedGeminiLaunch(
  commandPrefix: string[],
  label: string,
  launchArgs: string[]
): DetectedAgentLaunch {
  const runtimeArgs = stripArgsWithOptionalValues(launchArgs, new Set([
    "-r",
    "--resume",
    "--list-sessions",
    "--delete-session",
  ]));
  return {
    kind: "gemini",
    label,
    resumeEntryCommand: joinCommandTokens([
      ...commandPrefix,
      ...runtimeArgs,
      "--list-sessions",
    ]),
    newSessionCommand: joinCommandTokens([...commandPrefix, ...runtimeArgs]),
  };
}

function buildDetectedOpenCodeLaunch(
  commandPrefix: string[],
  label: string,
  launchArgs: string[]
): DetectedAgentLaunch {
  const runtimeArgs = stripOpenCodeSessionArgs(launchArgs);
  return {
    kind: "opencode",
    label,
    resumeEntryCommand: joinCommandTokens([
      ...commandPrefix,
      "session",
      "list",
    ]),
    newSessionCommand: joinCommandTokens([...commandPrefix, ...runtimeArgs]),
  };
}

function mergeCodexRuntimeOptions(
  globalOptions: string[],
  runtimeOptions: string[]
): string[] {
  return [...globalOptions, ...runtimeOptions];
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
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const option = codexOptionKey(token.value);
    if (!option) break;

    if (
      CODEX_VALUE_OPTIONS.has(option) &&
      !hasInlineCodexOptionValue(token.value, option)
    ) {
      const nextToken = tokens[index + 1];
      if (!nextToken || isSuspiciousCodexOptionValue(option, nextToken.value)) {
        break;
      }
      if (!CODEX_DROPPED_OPTIONS.has(option)) {
        out.push(token.raw, nextToken.raw);
      }
      index += 1;
      continue;
    }

    if (!CODEX_DROPPED_OPTIONS.has(option)) {
      out.push(token.raw);
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
      if (isSuspiciousCodexOptionValue(pendingValueOption, token.value)) {
        pendingValueOption = null;
        break;
      }
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
      if (
        CODEX_VALUE_OPTIONS.has(option) &&
        !hasInlineCodexOptionValue(token.value, option)
      ) {
        pendingValueOption = option;
      }
      if (!CODEX_DROPPED_OPTIONS.has(option)) {
        out.push(token.raw);
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

function stripArgsWithOptionalValues(
  args: string[],
  removableOptions: Set<string>
): string[] {
  const out: string[] = [];

  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    const normalized = normalizeOptionToken(value);
    if (normalized && removableOptions.has(normalized)) {
      if (optionLikelyConsumesValue(normalized, value, args[index + 1])) {
        index += 1;
      }
      continue;
    }
    out.push(value);
  }

  return out;
}

function stripOpenCodeSessionArgs(args: string[]): string[] {
  const stripped = stripArgsWithOptionalValues(
    args,
    new Set(["--continue", "--session"])
  );
  if (
    normalizeCommandToken(stripped[0] ?? "") === "session" &&
    normalizeCommandToken(stripped[1] ?? "") === "list"
  ) {
    return stripped.slice(2);
  }
  return stripped;
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

function normalizeOptionToken(token: string): string | null {
  if (token === "--") return null;
  if (token.startsWith("--")) {
    const eq = token.indexOf("=");
    return eq >= 0 ? token.slice(0, eq) : token;
  }
  return token.startsWith("-") && token !== "-" ? token : null;
}

function optionLikelyConsumesValue(
  option: string,
  rawToken: string,
  nextToken?: string
): boolean {
  if (option.startsWith("--") && rawToken.includes("=")) {
    return false;
  }
  if ((option === "-c" || option === "--continue" || option === "--list-sessions") &&
      nextToken &&
      !looksLikeOption(nextToken)) {
    return false;
  }
  return Boolean(nextToken && !looksLikeOption(nextToken));
}

function looksLikeOption(token: string): boolean {
  return token === "--" || (token.startsWith("-") && token !== "-");
}

function isSuspiciousCodexOptionValue(option: string, value: string): boolean {
  if (!CODEX_VALUE_OPTIONS.has(option)) {
    return false;
  }
  return CODEX_SUBCOMMANDS.has(normalizeCommandToken(value));
}

function hasInlineCodexOptionValue(token: string, option: string): boolean {
  if (option.startsWith("--")) {
    return token.startsWith(`${option}=`);
  }
  return token.length > option.length;
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

function containsCjk(value: string): boolean {
  return /[\u3400-\u9fff\uF900-\uFAFF]/u.test(value);
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
