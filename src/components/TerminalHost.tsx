import { useAppStore } from "../store";
import { TerminalView } from "./TerminalView";
import { Welcome } from "./Welcome";

export function TerminalHost() {
  const shells = useAppStore((s) => s.shells);
  const activeShellId = useAppStore((s) => s.activeShellId);
  const ids = Object.keys(shells);

  if (ids.length === 0) return <Welcome />;

  return (
    <div className="relative flex-1 min-w-0 bg-bg-0 overflow-hidden">
      {ids.map((id) => (
        <TerminalView
          key={id}
          shell={shells[id]}
          active={id === activeShellId}
        />
      ))}
    </div>
  );
}
