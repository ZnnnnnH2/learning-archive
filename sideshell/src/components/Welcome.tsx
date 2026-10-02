import { open } from "@tauri-apps/plugin-dialog";
import { FolderPlus } from "lucide-react";
import { useAppStore } from "../store";
import { useI18n } from "../useI18n";
import { AppIcon } from "./AppIcon";

export function Welcome() {
  const { t } = useI18n();
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
        <div className="relative flex items-center justify-center">
          <div
            className="absolute inset-2 rounded-full bg-accent/18 blur-2xl"
            aria-hidden="true"
          />
          <AppIcon size={72} alt={t("app.name")} className="relative" />
        </div>
        <div>
          <div className="text-xl font-semibold text-text-0 tracking-tight">
            {t("app.name")}
          </div>
          <div className="text-[13px] text-text-2 mt-1">
            {t("welcome.tagline")}
          </div>
        </div>
        <button
          onClick={pick}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent/25 border border-accent/40 hover:bg-accent/35 text-text-0 text-[13px] transition"
        >
          <FolderPlus size={16} />
          {t("welcome.addProject")}
        </button>
        <div className="text-[11.5px] text-text-2/80 leading-relaxed mt-2">
          {t("welcome.description")}
        </div>
      </div>
    </div>
  );
}
