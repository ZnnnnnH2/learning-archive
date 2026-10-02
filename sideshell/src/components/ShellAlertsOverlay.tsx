import { BellRing, X } from "lucide-react";
import { dismissShellAlert, activateShellFromAlert } from "../shellAlerts";
import { useShellAlertStore } from "../shellAlertStore";
import { useI18n } from "../useI18n";
import { cn } from "../utils";

export function ShellAlertsOverlay() {
  const { t } = useI18n();
  const alerts = useShellAlertStore((state) => state.alerts);

  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="no-drag pointer-events-none fixed right-4 top-4 z-50 flex w-[min(360px,calc(100vw-24px))] flex-col gap-2">
      {alerts.map((alert) => (
        <div
          key={alert.shellId}
          role="button"
          tabIndex={0}
          onClick={() => {
            void activateShellFromAlert(alert.shellId);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              void activateShellFromAlert(alert.shellId);
            }
          }}
          className={cn(
            "pointer-events-auto rounded-2xl border border-warn/35 bg-bg-1/96 px-3.5 py-3 shadow-2xl backdrop-blur",
            "cursor-pointer transition hover:border-warn/55 hover:bg-bg-2/96"
          )}
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full border border-warn/35 bg-warn/12 p-2 text-warn">
              <BellRing size={14} className="anim-pulse" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium text-text-0">
                {alert.title}
              </div>
              <div className="mt-1 max-h-[3.75rem] overflow-hidden text-[11.5px] leading-5 text-text-1">
                {alert.body}
              </div>
              <div className="mt-2 text-[10.5px] uppercase tracking-[0.16em] text-text-2">
                {t("alerts.overlay.jump")}
              </div>
            </div>
            <button
              onClick={(event) => {
                event.stopPropagation();
                dismissShellAlert(alert.shellId);
              }}
              className="rounded-md p-1 text-text-2 transition hover:bg-bg-3 hover:text-text-0"
              title={t("alerts.overlay.dismiss")}
            >
              <X size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
