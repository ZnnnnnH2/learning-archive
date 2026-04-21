import { useAppStore } from "../store";
import { TerminalView } from "./TerminalView";
import { Welcome } from "./Welcome";

export function TerminalHost() {
  const shells = useAppStore((s) => s.shells);
  const activeShellId = useAppStore((s) => s.activeShellId);
  const ids = Object.keys(shells);
  const mountedIds = ids.filter((id) => !shells[id].lazyStart);

  if (ids.length === 0) return <Welcome />;
  if (mountedIds.length === 0) {
    return (
      <div className="flex-1 min-w-0 bg-bg-0 overflow-hidden">
        <div className="h-full w-full flex items-center justify-center px-6 text-center">
          <div className="max-w-sm space-y-2">
            <div className="text-[14px] font-medium text-text-0">
              Select a shell to start or resume it.
            </div>
            <div className="text-[12px] leading-5 text-text-2">
              Restored shells stay idle until you open them, so agent sessions
              only resume on demand.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex-1 min-w-0 bg-bg-0 overflow-hidden">
      {mountedIds.map((id) => (
        <TerminalView
          key={id}
          shell={shells[id]}
          active={id === activeShellId}
        />
      ))}
    </div>
  );
}
