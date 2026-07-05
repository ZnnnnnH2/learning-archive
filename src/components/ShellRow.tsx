import { memo, useState } from "react";
import * as ContextMenu from "@radix-ui/react-context-menu";
import { TerminalSquare, X, Pencil, Copy, GitFork, Sparkles } from "lucide-react";
import { useAppStore } from "../store";
import type { Shell } from "../types";
import { useI18n } from "../useI18n";
import { StatusDot } from "./StatusDot";
import { cn, shortenPath } from "../utils";

interface Props {
  shellId: string;
}

function ShellRowComponent({ shellId }: Props) {
  const { t } = useI18n();
  const shell = useAppStore((s) => s.shells[shellId]);
  const active = useAppStore((s) => s.activeShellId === shellId);
  const setActive = useAppStore((s) => s.setActive);
  const removeShell = useAppStore((s) => s.removeShell);
  const renameShell = useAppStore((s) => s.renameShell);
  const useAutoShellName = useAppStore((s) => s.useAutoShellName);
  const cloneShell = useAppStore((s) => s.cloneShell);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  if (!shell) return null;

  const commit = () => {
    const n = draft.trim();
    if (n && n !== shell.name) renameShell(shellId, n);
    setEditing(false);
  };

  const cwdShort =
    shell.cwd && shell.cwd !== shell.initialCwd
      ? shortenPath(shell.cwd, 28)
      : null;
  const secondaryPreview = getShellSecondaryPreview(shell, cwdShort);

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>
        <div
          onClick={() => setActive(shellId)}
          onDoubleClick={() => {
            setEditing(true);
            setDraft(shell.name);
          }}
          className={cn(
            "group flex items-center gap-1.5 px-1.5 py-1 rounded-md cursor-default select-none",
            "hover:bg-bg-2 transition-colors",
            active && "bg-accent/15 hover:bg-accent/20",
            shell.lazyStart && !active && "bg-accent/[0.04]"
          )}
        >
          <TerminalSquare
            size={12}
            className={cn(
              "shrink-0",
              active
                ? "text-accent"
                : shell.lazyStart
                  ? "text-accent/80"
                  : "text-text-2"
            )}
          />
          <div className="flex-1 min-w-0 flex flex-col leading-tight">
            {editing ? (
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  else if (e.key === "Escape") setEditing(false);
                }}
                onClick={(e) => e.stopPropagation()}
                className="bg-bg-3 text-[12px] px-1 py-0.5 rounded outline-none border border-accent/40 text-text-0"
              />
            ) : (
              <div className="flex min-w-0 items-center gap-1.5">
                <span
                  className={cn(
                    "min-w-0 truncate text-[12px]",
                    active ? "text-text-0" : "text-text-1"
                  )}
                >
                  {shell.name}
                </span>
                {shell.lazyStart ? (
                  <span className="shrink-0 rounded-full border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-[0.08em] text-accent">
                    {t("shell.badge.pendingRestore")}
                  </span>
                ) : null}
              </div>
            )}
            {secondaryPreview && (
              <span
                className="truncate text-[10.5px] text-text-2"
                title={secondaryPreview.title}
              >
                {secondaryPreview.text}
              </span>
            )}
          </div>
          <StatusDot
            status={shell.status}
            needsAttention={shell.needsAttention}
          />
          <button
            onClick={(e) => {
              e.stopPropagation();
              removeShell(shellId);
            }}
            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-bg-3 text-text-2 transition-opacity"
            title={t("shell.closeShell")}
          >
            <X size={11} />
          </button>
        </div>
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content className="z-50 min-w-[180px] rounded-md bg-bg-2 border border-border shadow-xl p-1 text-[12.5px] text-text-0">
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => cloneShell(shellId)}
          >
            <GitFork size={13} /> {t("shell.menu.cloneShell")}
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => {
              setEditing(true);
              setDraft(shell.name);
            }}
          >
            <Pencil size={13} /> {t("shell.menu.rename")}
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => useAutoShellName(shellId)}
          >
            <Sparkles size={13} /> {t("shell.menu.useAutoName")}
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => navigator.clipboard.writeText(shell.cwd)}
          >
            <Copy size={13} /> {t("shell.menu.copyCwd")}
          </ContextMenu.Item>
          <ContextMenu.Separator className="h-px bg-border my-1" />
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bad/20 text-bad outline-none cursor-default flex items-center gap-2"
            onSelect={() => removeShell(shellId)}
          >
            <X size={13} /> {t("shell.menu.close")}
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  );
}

export const ShellRow = memo(ShellRowComponent);

function getShellSecondaryPreview(
  shell: Shell,
  cwdShort: string | null
): { text: string; title: string } | null {
  const ignored = new Set(
    [shell.name, shell.autoName]
      .map((value) => normalizeText(value)?.toLowerCase() ?? "")
      .filter(Boolean)
  );

  for (const candidate of [shell.taskSummary, shell.terminalTitle]) {
    const normalized = normalizeText(candidate);
    if (!normalized) continue;
    if (ignored.has(normalized.toLowerCase())) continue;
    return {
      text: normalized,
      title: normalized,
    };
  }

  if (!cwdShort) return null;
  return {
    text: cwdShort,
    title: shell.cwd,
  };
}

function normalizeText(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}
