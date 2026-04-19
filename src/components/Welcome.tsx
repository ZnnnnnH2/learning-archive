import { open } from "@tauri-apps/plugin-dialog";
import { FolderPlus, TerminalSquare } from "lucide-react";
import { useAppStore } from "../store";

export function Welcome() {
  const addProject = useAppStore((s) => s.addProject);

  const pick = async () => {
    try {
      const picked = await open({ directory: true, multiple: false });
      if (typeof picked === "string") addProject(picked);
    } catch {}
  };

  return (
    <div className="relative flex-1 min-w-0 bg-bg-0 flex items-center justify-center">
      <div className="max-w-sm text-center flex flex-col items-center gap-5 px-6">
        <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-accent/30 to-accent/5 border border-accent/30 flex items-center justify-center">
          <TerminalSquare className="text-accent" size={28} />
        </div>
        <div>
          <div className="text-xl font-semibold text-text-0 tracking-tight">
            SideShell
          </div>
          <div className="text-[13px] text-text-2 mt-1">
            Project-aware terminal with a tree-shaped sidebar.
          </div>
        </div>
        <button
          onClick={pick}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent/25 border border-accent/40 hover:bg-accent/35 text-text-0 text-[13px] transition"
        >
          <FolderPlus size={16} />
          Add a project folder
        </button>
        <div className="text-[11.5px] text-text-2/80 leading-relaxed mt-2">
          Each project can host multiple shells. Switching is instant — PTYs stay
          running in the background.
        </div>
      </div>
    </div>
  );
}
