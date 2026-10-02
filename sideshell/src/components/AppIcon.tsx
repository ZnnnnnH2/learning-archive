import type { CSSProperties } from "react";
import sideshellIcon from "../assets/branding/sideshell-icon.svg";
import { cn } from "../utils";

type AppIconProps = {
  className?: string;
  size?: number | string;
  alt?: string;
  decorative?: boolean;
};

export function AppIcon({
  className,
  size = 20,
  alt = "SideShell",
  decorative = false,
}: AppIconProps) {
  const style: CSSProperties = {
    width: size,
    height: size,
  };

  return (
    <img
      src={sideshellIcon}
      alt={decorative ? "" : alt}
      aria-hidden={decorative || undefined}
      draggable={false}
      className={cn("shrink-0 select-none", className)}
      style={style}
    />
  );
}
