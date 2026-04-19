import { BellRing } from "lucide-react";
import { cn } from "../utils";
import type { ShellStatus } from "../types";

interface Props {
  status: ShellStatus;
  hasUnread?: boolean;
  className?: string;
}

export function StatusDot({ status, hasUnread, className }: Props) {
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
    return (
      <BellRing
        size={12}
        className={cn("shrink-0 text-warn anim-pulse", className)}
        aria-label="waiting for input"
      />
    );
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
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        hasUnread ? "bg-accent anim-pulse" : "bg-text-2/40",
        className
      )}
      aria-label={hasUnread ? "new output" : "idle"}
    />
  );
}
