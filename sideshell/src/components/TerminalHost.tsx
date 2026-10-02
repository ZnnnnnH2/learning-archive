import {
  useEffect,
  useRef,
  useState,
  useMemo,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useAppStore } from "../store";
import type { MessageKey } from "../i18n";
import { useI18n } from "../useI18n";
import type { AgentKind, LazyShellStartMode, Shell } from "../types";
import { cn } from "../utils";
import { useShallow } from "zustand/react/shallow";
import { TerminalView } from "./TerminalView";
import { Welcome } from "./Welcome";

interface RestoreAction {
  mode: LazyShellStartMode;
  label: string;
  description: string;
  visible: boolean;
  tone?: "primary" | "neutral";
}

function CompactRestorePrompt({
  shell,
  defaultMode,
  onConfirm,
  onShowChoices,
}: {
  shell: Shell;
  defaultMode: LazyShellStartMode;
  onConfirm: (mode: LazyShellStartMode) => void;
  onShowChoices: () => void;
}) {
  const { t } = useI18n();
  const focusRef = useRef<HTMLDivElement | null>(null);
  const actionLabel = getRestoreActionLabel(defaultMode, t);
  const actionDescription = getRestoreActionDescription(defaultMode, shell, t);
  const summary = getRestorePreviewText(shell) ?? shell.cwd;
  const agentName = formatAgentName(shell.agentKind, shell.agentLabel);

  useEffect(() => {
    focusRef.current?.focus();
  }, [defaultMode, shell.id]);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onConfirm(defaultMode);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      onShowChoices();
    }
  };

  return (
    <div className="absolute inset-0 z-20 pointer-events-none flex items-start justify-center px-6 pt-6">
      <div
        ref={focusRef}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="pointer-events-auto w-full max-w-3xl rounded-2xl border border-accent/25 bg-bg-1/95 p-4 shadow-2xl backdrop-blur outline-none"
      >
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-text-2">
              <span>{t("restore.badge")}</span>
              {agentName ? (
                <span className="rounded-full border border-border bg-bg-2 px-2 py-0.5 normal-case tracking-normal text-[11px] text-text-1">
                  {agentName}
                </span>
              ) : null}
            </div>
            <div className="text-[18px] leading-6 font-semibold text-text-0">
              {shell.name}
            </div>
            <div className="truncate text-[13px] leading-6 text-text-1" title={summary}>
              {summary}
            </div>
            <div className="truncate text-[12px] leading-5 text-text-2" title={shell.cwd}>
              {t("restore.compact.hint")}
            </div>
            <div className="truncate text-[12px] leading-5 text-text-2" title={actionDescription}>
              {actionDescription}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => onConfirm(defaultMode)}
              className="rounded-xl border border-accent/60 bg-accent/12 px-4 py-2 text-[12.5px] font-medium text-text-0 transition hover:bg-accent/18"
            >
              {actionLabel}
            </button>
            <button
              type="button"
              onClick={onShowChoices}
              className="rounded-xl border border-border bg-bg-2 px-4 py-2 text-[12.5px] text-text-1 transition hover:bg-bg-3 hover:text-text-0"
            >
              {t("restore.action.change")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function LazyRestorePrompt({
  shell,
  currentDefaultMode,
  onSelectAction,
  onClearDefault,
}: {
  shell: Shell;
  currentDefaultMode: LazyShellStartMode | null;
  onSelectAction: (mode: LazyShellStartMode, rememberAsDefault: boolean) => void;
  onClearDefault: () => void;
}) {
  const { t } = useI18n();
  const project = useAppStore((s) => s.projects[shell.projectId]);
  const title = project ? `${project.name} · ${shell.name}` : shell.name;
  const summary = getRestorePreviewText(shell);
  const description = summary ?? t("restore.description");
  const agentName = formatAgentName(shell.agentKind, shell.agentLabel);
  const [rememberAsDefault, setRememberAsDefault] = useState(false);

  useEffect(() => {
    setRememberAsDefault(false);
  }, [currentDefaultMode, shell.id]);

  const actions = getRestoreActions(shell, t).filter((action) => action.visible);

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-bg-0 px-6 py-8">
      <div className="w-full max-w-2xl rounded-2xl border border-border bg-bg-1/95 p-6 shadow-2xl backdrop-blur">
        <div className="space-y-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-text-2">
            {t("restore.badge")}
          </div>
          <div className="text-[22px] leading-7 font-semibold text-text-0">
            {title}
          </div>
          <div className="text-[14px] leading-6 text-text-1">
            {description}
          </div>
          {summary ? (
            <div className="text-[12px] leading-5 text-text-2">
              {t("restore.description")}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 text-[11.5px] text-text-1">
            {agentName ? (
              <div className="rounded-full border border-border bg-bg-2 px-3 py-1">
                {t("restore.meta.agent")}: {agentName}
              </div>
            ) : null}
            <div
              className="max-w-full truncate rounded-full border border-border bg-bg-2 px-3 py-1"
              title={shell.cwd}
            >
              {t("restore.meta.cwd")}: {shell.cwd}
            </div>
            {currentDefaultMode ? (
              <div className="rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-text-0">
                {t("restore.meta.default")}: {getRestoreActionLabel(currentDefaultMode, t)}
              </div>
            ) : null}
          </div>
          {shell.agentKind ? (
            <div className="rounded-xl border border-border bg-bg-2/70 p-3">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={rememberAsDefault}
                  onChange={(event) => setRememberAsDefault(event.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-border bg-bg-1 text-accent focus:ring-accent/40"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] font-medium text-text-0">
                    {t("restore.default.remember", {
                      agent: formatAgentName(shell.agentKind, null) ?? shell.agentKind,
                    })}
                  </div>
                  {currentDefaultMode ? (
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] leading-5 text-text-2">
                      <span>
                        {t("restore.default.current", {
                          agent: formatAgentName(shell.agentKind, null) ?? shell.agentKind,
                          action: getRestoreActionLabel(currentDefaultMode, t),
                        })}
                      </span>
                      <button
                        type="button"
                        onClick={onClearDefault}
                        className="rounded-md border border-border px-2 py-0.5 text-[11px] text-text-1 transition hover:bg-bg-3 hover:text-text-0"
                      >
                        {t("restore.default.clear")}
                      </button>
                    </div>
                  ) : null}
                </div>
              </label>
            </div>
          ) : null}
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {actions.map((action) => (
            <button
              key={action.mode}
              type="button"
              onClick={() => onSelectAction(action.mode, rememberAsDefault)}
              className={cn(
                "rounded-xl border px-4 py-4 text-left transition-colors",
                action.tone === "primary"
                  ? "border-accent/60 bg-accent/10 hover:bg-accent/16"
                  : "border-border bg-bg-2/70 hover:bg-bg-2",
                currentDefaultMode === action.mode &&
                  "border-accent/65 ring-1 ring-accent/20"
              )}
            >
              <div className="text-[13px] font-medium text-text-0">
                {action.label}
              </div>
              <div className="mt-2 text-[12px] leading-5 text-text-2">
                {action.description}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function TerminalHost() {
  const { t } = useI18n();
  const ids = useAppStore(useShallow((s) => Object.keys(s.shells)));
  const totalShellsCount = ids.length;

  const activeShellId = useAppStore((s) => s.activeShellId);
  const activeShell = useAppStore((s) => (s.activeShellId ? s.shells[s.activeShellId] : null));

  // Virtualization: keep only the most recently active terminals mounted
  const lastActiveMapRef = useRef<Record<string, number>>({});
  const MAX_MOUNTED_TERMINALS = 12;

  useEffect(() => {
    if (activeShellId) {
      lastActiveMapRef.current[activeShellId] = Date.now();
    }
  }, [activeShellId]);

  const nonLazyIds = useAppStore(
    useShallow((s) => {
      const result: string[] = [];
      for (const id in s.shells) {
        if (!s.shells[id].lazyStart) {
          result.push(id);
        }
      }
      return result;
    })
  );

  const mountedIds = useMemo(() => {
    const sorted = [...nonLazyIds].sort((a, b) => {
      const timeA = lastActiveMapRef.current[a] || 0;
      const timeB = lastActiveMapRef.current[b] || 0;
      return timeB - timeA;
    });

    const nextMounted = new Set<string>();
    if (activeShellId && nonLazyIds.includes(activeShellId)) {
      nextMounted.add(activeShellId);
    }
    
    for (const id of sorted) {
      if (nextMounted.size >= MAX_MOUNTED_TERMINALS) break;
      nextMounted.add(id);
    }

    return Array.from(nextMounted);
  }, [nonLazyIds, activeShellId]);

  const startLazyShell = useAppStore((s) => s.startLazyShell);
  const setAgentRestoreDefault = useAppStore((s) => s.setAgentRestoreDefault);
  const clearAgentRestoreDefault = useAppStore((s) => s.clearAgentRestoreDefault);
  const restoreDefaultsByAgent = useAppStore(
    (s) => s.terminalSettings.restoreDefaultsByAgent
  );
  const [expandedPromptShellId, setExpandedPromptShellId] = useState<string | null>(
    null
  );

  useEffect(() => {
    setExpandedPromptShellId(null);
  }, [activeShell?.id]);

  useEffect(() => {
    if (!activeShell?.lazyStart || shouldShowLazyRestorePrompt(activeShell)) {
      return;
    }
    startLazyShell(activeShell.id, "terminal");
  }, [
    activeShell?.id,
    activeShell?.lazyStart,
    activeShell?.agentKind,
    activeShell?.resumeEntryCommand,
    activeShell?.newSessionCommand,
    startLazyShell,
  ]);

  if (totalShellsCount === 0) return <Welcome />;

  const currentDefaultMode = activeShell?.agentKind
    ? restoreDefaultsByAgent[activeShell.agentKind] ?? null
    : null;
  const shouldRenderPrompt = Boolean(
    activeShell?.lazyStart && shouldShowLazyRestorePrompt(activeShell)
  );
  const shouldRenderFullPrompt =
    !currentDefaultMode || expandedPromptShellId === activeShell?.id;

  const handleSelectAction = (
    shell: Shell,
    mode: LazyShellStartMode,
    rememberAsDefault: boolean
  ) => {
    if (rememberAsDefault && shell.agentKind) {
      setAgentRestoreDefault(shell.agentKind, mode);
    }
    setExpandedPromptShellId(null);
    startLazyShell(shell.id, mode);
  };

  const handleClearDefault = (shell: Shell) => {
    if (!shell.agentKind) return;
    clearAgentRestoreDefault(shell.agentKind);
  };

  return (
    <div className="relative flex-1 min-w-0 overflow-hidden bg-bg-0">
      {mountedIds.map((id) => (
        <TerminalView key={id} shellId={id} active={id === activeShellId} />
      ))}
      {shouldRenderPrompt && activeShell ? (
        shouldRenderFullPrompt ? (
          <LazyRestorePrompt
            shell={activeShell}
            currentDefaultMode={currentDefaultMode}
            onSelectAction={(mode, rememberAsDefault) =>
              handleSelectAction(activeShell, mode, rememberAsDefault)
            }
            onClearDefault={() => handleClearDefault(activeShell)}
          />
        ) : (
          <CompactRestorePrompt
            shell={activeShell}
            defaultMode={currentDefaultMode}
            onConfirm={(mode) => handleSelectAction(activeShell, mode, false)}
            onShowChoices={() => setExpandedPromptShellId(activeShell.id)}
          />
        )
      ) : mountedIds.length === 0 ? (
        <div className="flex h-full w-full items-center justify-center px-6 text-center">
          <div className="max-w-sm space-y-2">
            <div className="text-[14px] font-medium text-text-0">
              {t("terminalHost.emptyTitle")}
            </div>
            <div className="text-[12px] leading-5 text-text-2">
              {t("terminalHost.emptyDescription")}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function shouldShowLazyRestorePrompt(shell: Shell): boolean {
  return Boolean(
    shell.agentKind && (shell.resumeEntryCommand || shell.newSessionCommand)
  );
}

function getRestoreActions(
  shell: Shell,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string
): RestoreAction[] {
  const canResume = Boolean(shell.resumeEntryCommand);
  const canStartNewSession = Boolean(shell.agentKind || shell.newSessionCommand);

  return [
    {
      mode: "restore",
      label: t("restore.action.resume"),
      description: getRestoreActionDescription("restore", shell, t),
      visible: canResume,
      tone: "primary",
    },
    {
      mode: "new_agent_session",
      label: t("restore.action.newSession"),
      description: getRestoreActionDescription("new_agent_session", shell, t),
      visible: canStartNewSession,
    },
    {
      mode: "terminal",
      label: t("restore.action.openTerminal"),
      description: getRestoreActionDescription("terminal", shell, t),
      visible: true,
    },
  ];
}

function getRestoreActionLabel(
  mode: LazyShellStartMode,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string
): string {
  switch (mode) {
    case "restore":
      return t("restore.action.resume");
    case "new_agent_session":
      return t("restore.action.newSession");
    case "terminal":
      return t("restore.action.openTerminal");
  }
}

function getRestoreActionDescription(
  mode: LazyShellStartMode,
  shell: Shell,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string
): string {
  if (mode === "restore") {
    return getResumeDescription(shell, t);
  }
  if (mode === "new_agent_session") {
    return t("restore.action.newSession.description");
  }
  return t("restore.action.openTerminal.description");
}

function getResumeDescription(
  shell: Shell,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string
): string {
  switch (shell.agentKind) {
    case "codex":
      return t("restore.action.resume.description.codex");
    case "claude":
      return t("restore.action.resume.description.claude");
    case "gemini":
      return t("restore.action.resume.description.gemini");
    case "opencode":
      return t("restore.action.resume.description.opencode");
    default:
      return t("restore.action.resume.description.generic");
  }
}

function getRestorePreviewText(shell: Shell): string | null {
  const ignored = new Set(
    [shell.name, shell.autoName, shell.cwd]
      .map((value) => normalizeText(value)?.toLowerCase() ?? "")
      .filter(Boolean)
  );

  for (const candidate of [shell.taskSummary, shell.terminalTitle]) {
    const normalized = normalizeText(candidate);
    if (!normalized) continue;
    if (ignored.has(normalized.toLowerCase())) continue;
    return normalized;
  }

  return null;
}

function normalizeText(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function formatAgentName(
  agentKind: AgentKind | null,
  agentLabel: string | null
): string | null {
  const label = normalizeText(agentLabel);
  if (label) {
    if (label.toLowerCase() === "codex") return "Codex";
    if (label.toLowerCase() === "claude") return "Claude";
    if (label.toLowerCase() === "gemini") return "Gemini";
    if (label.toLowerCase() === "opencode") return "OpenCode";
    return label;
  }

  switch (agentKind) {
    case "codex":
      return "Codex";
    case "claude":
      return "Claude";
    case "gemini":
      return "Gemini";
    case "opencode":
      return "OpenCode";
    default:
      return null;
  }
}
