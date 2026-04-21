import { useAppStore } from "../store";
import type { LazyShellStartMode, Shell } from "../types";
import { cn } from "../utils";
import { TerminalView } from "./TerminalView";
import { Welcome } from "./Welcome";

function LazyRestorePrompt({ shell }: { shell: Shell }) {
  const project = useAppStore((s) => s.projects[shell.projectId]);
  const startLazyShell = useAppStore((s) => s.startLazyShell);
  const canResume = Boolean(
    shell.restorePending ||
      shell.restoreResolvePending ||
      shell.restoreTarget ||
      shell.restoreFallbackCommand
  );
  const canStartNewSession = Boolean(shell.agentKind || shell.newSessionCommand);
  const title = project ? `${project.name} · ${shell.name}` : shell.name;

  const actions: Array<{
    mode: LazyShellStartMode;
    label: string;
    description: string;
    visible: boolean;
    tone?: "primary" | "neutral";
  }> = [
    {
      mode: "restore",
      label: "Resume conversation",
      description: "Reconnect this shell to the recorded agent session.",
      visible: canResume,
      tone: "primary",
    },
    {
      mode: "new_agent_session",
      label: "Start new session",
      description: "Launch the same agent here without restoring the old thread.",
      visible: canStartNewSession,
    },
    {
      mode: "terminal",
      label: "Open terminal",
      description: "Discard agent restore state and open a plain shell.",
      visible: true,
    },
  ];

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center px-6 py-8 bg-bg-0">
      <div className="w-full max-w-2xl rounded-2xl border border-border bg-bg-1/95 shadow-2xl p-6 backdrop-blur">
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-[0.18em] text-text-2">
            Restored Shell
          </div>
          <div className="text-[22px] leading-7 font-semibold text-text-0">
            {title}
          </div>
          <div className="max-w-xl text-[13px] leading-6 text-text-2">
            This shell was restored from app state. Choose whether to resume the
            previous conversation, start a fresh agent session, or open a plain
            terminal.
          </div>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {actions
            .filter((action) => action.visible)
            .map((action) => (
              <button
                key={action.mode}
                type="button"
                onClick={() => startLazyShell(shell.id, action.mode)}
                className={cn(
                  "rounded-xl border px-4 py-4 text-left transition-colors",
                  action.tone === "primary"
                    ? "border-accent/60 bg-accent/10 hover:bg-accent/16"
                    : "border-border bg-bg-2/70 hover:bg-bg-2"
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
  const shells = useAppStore((s) => s.shells);
  const activeShellId = useAppStore((s) => s.activeShellId);
  const ids = Object.keys(shells);
  const mountedIds = ids.filter((id) => !shells[id].lazyStart);
  const activeShell = activeShellId ? shells[activeShellId] : null;

  if (ids.length === 0) return <Welcome />;

  return (
    <div className="relative flex-1 min-w-0 bg-bg-0 overflow-hidden">
      {mountedIds.map((id) => (
        <TerminalView key={id} shell={shells[id]} active={id === activeShellId} />
      ))}
      {activeShell?.lazyStart ? (
        <LazyRestorePrompt shell={activeShell} />
      ) : mountedIds.length === 0 ? (
        <div className="h-full w-full flex items-center justify-center px-6 text-center">
          <div className="max-w-sm space-y-2">
            <div className="text-[14px] font-medium text-text-0">
              Select a shell to start or resume it.
            </div>
            <div className="text-[12px] leading-5 text-text-2">
              Restored shells stay idle until you choose how to start them.
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
