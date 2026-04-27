import { useState } from "react";
import * as ContextMenu from "@radix-ui/react-context-menu";
import { message } from "@tauri-apps/plugin-dialog";
import {
  ChevronRight,
  Folder,
  FolderOpen,
  Plus,
  X,
  Pencil,
  Copy,
  Code2,
} from "lucide-react";
import { useAppStore } from "../store";
import {
  openProjectInEditor,
  openProjectInFileManager,
  type ExternalEditor,
} from "../ipc";
import { useI18n } from "../useI18n";
import type { ShellStatus } from "../types";
import { ShellRow } from "./ShellRow";
import { StatusDot } from "./StatusDot";
import { cn } from "../utils";

interface Props {
  projectId: string;
}

export function ProjectRow({ projectId }: Props) {
  const { t } = useI18n();
  const project = useAppStore((s) => s.projects[projectId]);
  const aggregateKey = useAppStore((s) => selectProjectAggregateKey(s, projectId));
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
  const aggregate = parseProjectAggregateKey(aggregateKey);
  const aggStatus = aggregate.status;
  const aggAttention = aggregate.needsAttention;
  const isAnyActive = activeShellId ? shellIds.includes(activeShellId) : false;

  const commitRename = () => {
    const name = draftName.trim();
    if (name && name !== project.name) renameProject(project.id, name);
    setEditing(false);
  };

  const handleOpenInEditor = async (editor: ExternalEditor) => {
    try {
      await openProjectInEditor(editor, project.path);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await message(detail, {
        title: t("project.error.openProject"),
        kind: "error",
      });
    }
  };

  const handleOpenInExplorer = async () => {
    try {
      await openProjectInFileManager(project.path);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await message(detail, {
        title: t("project.error.openProjectFolder"),
        kind: "error",
      });
    }
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
            <StatusDot
              status={aggStatus}
              needsAttention={aggAttention}
            />
            <button
              onClick={(e) => {
                e.stopPropagation();
                addShell(project.id);
              }}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-bg-3 text-text-2 transition-opacity"
              title={t("project.newShellInProject")}
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
            <Plus size={13} /> {t("project.menu.newShell")}
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => {
              setEditing(true);
              setDraftName(project.name);
            }}
          >
            <Pencil size={13} /> {t("project.menu.rename")}
          </ContextMenu.Item>
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2"
            onSelect={() => navigator.clipboard.writeText(project.path)}
          >
            <Copy size={13} /> {t("project.menu.copyPath")}
          </ContextMenu.Item>
          <ContextMenu.Sub>
            <ContextMenu.SubTrigger className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default flex items-center gap-2">
              <Code2 size={13} /> {t("project.menu.openIn")}
              <span className="ml-auto text-text-2">
                <ChevronRight size={13} />
              </span>
            </ContextMenu.SubTrigger>
            <ContextMenu.Portal>
              <ContextMenu.SubContent className="z-50 min-w-[160px] rounded-md bg-bg-2 border border-border shadow-xl p-1 text-[12.5px] text-text-0">
                <ContextMenu.Item
                  className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default"
                  onSelect={() => void handleOpenInEditor("vscode")}
                >
                  VS Code
                </ContextMenu.Item>
                <ContextMenu.Item
                  className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default"
                  onSelect={() => void handleOpenInEditor("zed")}
                >
                  Zed
                </ContextMenu.Item>
                <ContextMenu.Item
                  className="px-2 py-1.5 rounded hover:bg-bg-3 outline-none cursor-default"
                  onSelect={() => void handleOpenInExplorer()}
                >
                  {t("project.menu.fileExplorer")}
                </ContextMenu.Item>
              </ContextMenu.SubContent>
            </ContextMenu.Portal>
          </ContextMenu.Sub>
          <ContextMenu.Separator className="h-px bg-border my-1" />
          <ContextMenu.Item
            className="px-2 py-1.5 rounded hover:bg-bad/20 text-bad outline-none cursor-default flex items-center gap-2"
            onSelect={() => removeProject(project.id)}
          >
            <X size={13} /> {t("project.menu.removeProject")}
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  );
}

function selectProjectAggregateKey(
  state: ReturnType<typeof useAppStore.getState>,
  projectId: string
): string {
  const shellIds = state.projects[projectId]?.shellIds ?? [];
  let hasError = false;
  let hasWaiting = false;
  let hasAttention = false;

  for (const shellId of shellIds) {
    const shell = state.shells[shellId];
    if (!shell) continue;
    if (shell.status === "error") hasError = true;
    else if (shell.status === "waiting") hasWaiting = true;
    if (shell.needsAttention) hasAttention = true;
  }

  const status = hasError ? "error" : hasWaiting ? "waiting" : "idle";
  return `${status}:${hasAttention ? 1 : 0}`;
}

function parseProjectAggregateKey(key: string): {
  status: ShellStatus;
  needsAttention: boolean;
} {
  const [status, attentionValue] = key.split(":");
  return {
    status:
      status === "error" || status === "waiting" || status === "idle"
        ? status
        : "idle",
    needsAttention: attentionValue === "1",
  };
}
