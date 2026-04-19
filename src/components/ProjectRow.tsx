import { useState } from "react";
import * as ContextMenu from "@radix-ui/react-context-menu";
import {
  ChevronRight,
  Folder,
  FolderOpen,
  Plus,
  X,
  Pencil,
  Copy,
} from "lucide-react";
import { useAppStore } from "../store";
import { ShellRow } from "./ShellRow";
import { StatusDot } from "./StatusDot";
import { cn } from "../utils";

interface Props {
  projectId: string;
}

export function ProjectRow({ projectId }: Props) {
  const project = useAppStore((s) => s.projects[projectId]);
  const shells = useAppStore((s) => s.shells);
  const toggleExpand = useAppStore((s) => s.toggleProjectExpand);
  const addShell = useAppStore((s) => s.addShell);
  const removeProject = useAppStore((s) => s.removeProject);
  const renameProject = useAppStore((s) => s.renameProject);
  const activeShellId = useAppStore((s) => s.activeShellId);
  const setActive = useAppStore((s) => s.setActive);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(project?.name ?? "");

  if (!project) return null;
  const { expanded, shellIds } = project;

  // Aggregate status
  const aggStatus = (() => {
    let hasError = false;
    let hasWaiting = false;
    let hasRunning = false;
    let hasUnread = false;
    for (const sid of shellIds) {
      const sh = shells[sid];
      if (!sh) continue;
      if (sh.status === "error") hasError = true;
      else if (sh.status === "waiting") hasWaiting = true;
      else if (sh.status === "running") hasRunning = true;
      if (sh.hasUnread) hasUnread = true;
    }
    if (hasError) return "error" as const;
    if (hasWaiting) return "waiting" as const;
    if (hasRunning) return "running" as const;
    if (hasUnread) return "idle" as const;
    return "idle" as const;
  })();
  const aggUnread = shellIds.some((sid) => shells[sid]?.hasUnread);

  const isAnyActive = shellIds.includes(activeShellId ?? "");

  const commitRename = () => {
    const name = draftName.trim();
    if (name && name !== project.name) renameProject(project.id, name);
    setEditing(false);
  };

  const onClickProject = () => {
    // Click activates most-recent shell, or create if empty
    if (shellIds.length === 0) {
      addShell(project.id);
    } else {
      const firstId = shellIds[0];
      setActive(firstId);
      if (!expanded) toggleExpand(project.id);
    }
  };

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>
        <div className="flex flex-col">
          <div
            onClick={onClickProject}
            onDoubleClick={() => {
              setEditing(true);
              setDraftName(project.name);
            }}
            className={cn(
              "group flex items-center gap-1.5 px-1.5 py-1.5 rounded-md cursor-default select-none",
              "hover:bg-bg-2 transition-colors",
              isAnyActive && "bg-bg-2/70"
            )}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleExpand(project.id);
              }}
              className="p-0.5 rounded hover:bg-bg-3 text-text-2"
            >
              <ChevronRight
                size={12}
                className={cn(
                  "transition-transform",
                  expanded && "rotate-90"
                )}
              />
            </button>
            <span className="text-text-1 shrink-0">
              {expanded ? <FolderOpen size={14} /> : <Folder size={14} />}
            </span>
            {editing ? (
              <input
                autoFocus
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  else if (e.key === "Escape") setEditing(false);
                }}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 min-w-0 bg-bg-3 text-[12.5px] px-1 py-0.5 rounded outline-none border border-accent/40 text-text-0"
              />
            ) : (
              <span
                className="flex-1 truncate text-[12.5px] text-text-0"
                title={project.path}
              >
                {project.name}
              </span>
            )}
            <StatusDot status={aggStatus} hasUnread={aggUnread} />
            <button
              onClick={(e) => {
                e.stopPropagation();
                addShell(project.id);
              }}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-bg-3 text-text-2 transition-opacity"
              title="New shell in this project"
            >
              <Plus size={12} />
            </button>
          </div>

          {expanded && shellIds.length > 0 && (
            <div className="flex flex-col ml-5 pl-2 border-l border-border/60 anim-slide-in">
              {shellIds.map((sid) => (
                <ShellRow key={sid} shellId={sid} />
              ))}
            </div>
          )}
        </div>
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content className="z-50 min-w-[180px] rounded-md bg-bg-2 border border-border shadow-xl p-1 text-[12.5px] text-text-0">
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => addShell(project.id)}
          >
            <Plus size={13} /> New shell
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => {
              setEditing(true);
              setDraftName(project.name);
            }}
          >
            <Pencil size={13} /> Rename
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => navigator.clipboard.writeText(project.path)}
          >
            <Copy size={13} /> Copy path
          </ContextMenu.Item>
          <ContextMenu.Separator className="h-px bg-border my-1" />
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bad/20 text-bad outline-none cursor-default flex items-center gap-2"
            onSelect={() => removeProject(project.id)}
          >
            <X size={13} /> Remove project
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  );
}
