import { BellRing } from "lucide-react";
import { useI18n } from "../useI18n";
import { cn } from "../utils";
import type { ShellStatus } from "../types";

interface Props {
  status: ShellStatus;
  needsAttention?: boolean;
  className?: string;
}

function AttentionIcon({
  className,
  label,
}: {
  className?: string;
  label: string;
}) {
  return (
    <BellRing
      size={12}
      className={cn("shrink-0 text-warn anim-pulse", className)}
      aria-label={label}
    />
  );
}

function WaitingDot({
  className,
  label,
}: {
  className?: string;
  label: string;
}) {
  return (
    <span
      className={cn(
        "inline-block h-2.5 w-2.5 rounded-full border border-warn bg-warn/25 anim-pulse",
        className
      )}
      aria-label={label}
    />
  );
}

export function StatusDot({ status, needsAttention, className }: Props) {
  const { t } = useI18n();

  if (needsAttention) {
    return (
      <AttentionIcon
        className={className}
        label={t("status.needsAttention")}
      />
    );
  }
  if (status === "running") {
    return (
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 rounded-full border border-text-2/60 bg-text-2/20 anim-pulse",
          className
        )}
        aria-label={t("status.running")}
      />
    );
  }
  if (status === "waiting") {
    return <WaitingDot className={className} label={t("status.waiting")} />;
  }
  if (status === "error") {
    return (
      <span
        className={cn("inline-block h-2 w-2 rounded-full bg-bad", className)}
        aria-label={t("status.error")}
      />
    );
  }
  if (status === "exited") {
    return (
      <span
        className={cn(
          "inline-block h-2 w-2 rounded-full bg-text-2/70",
          className
        )}
        aria-label={t("status.exited")}
      />
    );
  }
  // idle
  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full bg-text-2/40", className)}
      aria-label={t("status.idle")}
    />
  );
}
