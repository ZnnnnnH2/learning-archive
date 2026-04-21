import { useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { PanelLeftClose, Plus, Search, Settings } from "lucide-react";
import { useAppStore } from "../store";
import { ProjectRow } from "./ProjectRow";
import { Resizer } from "./Resizer";
import { SettingsDialog } from "./SettingsDialog";
import { cn } from "../utils";

export function Sidebar() {
  const sidebarWidth = useAppStore((s) => s.sidebarWidth);
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const setSidebarWidth = useAppStore((s) => s.setSidebarWidth);
  const projectOrder = useAppStore((s) => s.projectOrder);
  const projects = useAppStore((s) => s.projects);
  const addProject = useAppStore((s) => s.addProject);
  const [query, setQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projectOrder;
    return projectOrder.filter((pid) => {
      const p = projects[pid];
      return (
        p.name.toLowerCase().includes(q) ||
        p.path.toLowerCase().includes(q)
      );
    });
  }, [query, projectOrder, projects]);

  const handleAdd = async () => {
    try {
      const picked = await open({ directory: true, multiple: false });
      if (typeof picked === "string") {
        addProject(picked);
      }
    } catch (e) {
      console.warn(e);
    }
  };

  if (collapsed) {
    return (
      <>
        <div className="h-full w-10 bg-bg-1 border-r border-border flex flex-col items-center py-2 gap-2">
          <button
            className="no-drag p-1.5 rounded hover:bg-bg-3 text-text-1"
            onClick={() => setSettingsOpen(true)}
            title="Terminal settings"
          >
            <Settings size={16} />
          </button>
          <button
            className="no-drag p-1.5 rounded hover:bg-bg-3 text-text-1"
            onClick={handleAdd}
            title="Add project folder"
          >
            <Plus size={16} />
          </button>
          <button
            className="no-drag p-1.5 rounded hover:bg-bg-3 text-text-1"
            onClick={toggleSidebar}
            title="Show sidebar (Ctrl+B)"
          >
            <PanelLeftClose size={16} className="rotate-180" />
          </button>
        </div>
        <SettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
        />
      </>
    );
  }

  return (
    <>
      <aside
        className="h-full bg-bg-1 border-r border-border flex flex-col relative shrink-0"
        style={{ width: sidebarWidth }}
      >
        {/* Header */}
        <div className="drag-region flex items-center gap-2 px-3 pt-2.5 pb-1.5 shrink-0">
          <div className="flex-1 text-[13px] font-semibold text-text-0 tracking-tight select-none">
            SideShell
          </div>
          <button
            className="no-drag p-1 rounded hover:bg-bg-3 text-text-1"
            onClick={() => setSettingsOpen(true)}
            title="Terminal settings"
          >
            <Settings size={14} />
          </button>
          <button
            className="no-drag p-1 rounded hover:bg-bg-3 text-text-1"
            onClick={toggleSidebar}
            title="Hide sidebar (Ctrl+B)"
          >
            <PanelLeftClose size={14} />
          </button>
          <button
            className="no-drag p-1 rounded hover:bg-bg-3 text-text-1"
            onClick={handleAdd}
            title="Add project folder"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Search */}
        <div className="no-drag px-3 pb-2 shrink-0">
          <div
            className={cn(
              "flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-bg-2 border border-border",
              "focus-within:border-accent/60"
            )}
          >
            <Search size={12} className="text-text-2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects…"
              className="flex-1 bg-transparent text-[12px] text-text-0 placeholder:text-text-2 outline-none"
            />
          </div>
        </div>

        {/* Tree */}
        <div className="side-scroll flex-1 overflow-y-auto overflow-x-hidden px-1.5 pb-2">
          {filtered.length === 0 ? (
            <EmptySidebar onAdd={handleAdd} />
          ) : (
            <div className="flex flex-col">
              {filtered.map((pid) => (
                <ProjectRow key={pid} projectId={pid} />
              ))}
            </div>
          )}
        </div>

        <Resizer
          onResize={(dx) => setSidebarWidth(sidebarWidth + dx)}
        />
      </aside>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </>
  );
}

function EmptySidebar({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="px-3 py-8 flex flex-col items-center gap-3 text-center">
      <div className="text-[12px] text-text-2 leading-relaxed">
        No projects yet.
        <br />
        Add a folder to spin up shells.
      </div>
      <button
        onClick={onAdd}
        className="no-drag px-3 py-1.5 rounded-md bg-accent/20 border border-accent/40 text-[12px] text-text-0 hover:bg-accent/30 transition"
      >
        + Add folder
      </button>
    </div>
  );
}
