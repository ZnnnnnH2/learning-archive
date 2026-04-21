import { BellRing } from "lucide-react";
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
  if (needsAttention) {
    return <AttentionIcon className={className} label="needs attention" />;
  }
  if (status === "running") {
    return (
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 rounded-full border-2 border-good border-t-transparent anim-spin",
          className
        )}
        aria-label="running"
      />
    );
  }
  if (status === "waiting") {
    return <WaitingDot className={className} label="waiting for input" />;
  }
  if (status === "error") {
    return (
      <span
        className={cn("inline-block h-2 w-2 rounded-full bg-bad", className)}
        aria-label="error"
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
        aria-label="exited"
      />
    );
  }
  // idle
  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full bg-text-2/40", className)}
      aria-label="idle"
    />
  );
}
