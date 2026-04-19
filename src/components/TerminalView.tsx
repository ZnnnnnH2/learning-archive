import { useEffect, useLayoutEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import type { UnlistenFn } from "@tauri-apps/api/event";
import {
  ptyAttach,
  onPtyData,
  onPtyExit,
  pathExists,
  type PtyDataEvent,
  ptyResize,
  ptySpawn,
  ptyWrite,
} from "../ipc";
import { base64ToBytes, stringToBase64 } from "../utils";
import { useAppStore } from "../store";
import type { Shell } from "../types";

interface Props {
  shell: Shell;
  active: boolean;
}

const THEME = {
  background: "#0a0b0f",
  foreground: "#e7e9ee",
  cursor: "#7c7cff",
  cursorAccent: "#0a0b0f",
  selectionBackground: "rgba(124, 124, 255, 0.35)",
  black: "#0a0b0f",
  red: "#f87171",
  green: "#4ade80",
  yellow: "#fbbf24",
  blue: "#60a5fa",
  magenta: "#c084fc",
  cyan: "#22d3ee",
  white: "#e7e9ee",
  brightBlack: "#4a4f62",
  brightRed: "#fca5a5",
  brightGreen: "#86efac",
  brightYellow: "#fde68a",
  brightBlue: "#93c5fd",
  brightMagenta: "#d8b4fe",
  brightCyan: "#67e8f9",
  brightWhite: "#ffffff",
};

export function TerminalView({ shell, active }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const sessionIdRef = useRef<string | null>(shell.sessionId);
  const attachedSeqRef = useRef(0);
  const attachCompleteRef = useRef(false);
  const pendingDataRef = useRef<PtyDataEvent[]>([]);
  const disposedRef = useRef(false);

  // Store getters (avoid re-subscribing on every change)
  const setShellSession = useAppStore((s) => s.setShellSession);
  const setShellStatus = useAppStore((s) => s.setShellStatus);
  const setShellUnread = useAppStore((s) => s.setShellUnread);
  const setShellCwd = useAppStore((s) => s.setShellCwd);
  const setShellSize = useAppStore((s) => s.setShellSize);
  const setShellExit = useAppStore((s) => s.setShellExit);

  // Mount xterm once per shell id
  useLayoutEffect(() => {
    if (!hostRef.current) return;
    disposedRef.current = false;
    attachedSeqRef.current = 0;
    attachCompleteRef.current = false;
    pendingDataRef.current = [];

    const term = new Terminal({
      fontFamily:
        'JetBrains Mono, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.25,
      letterSpacing: 0,
      cursorBlink: true,
      cursorStyle: "bar",
      cursorWidth: 2,
      theme: THEME,
      allowProposedApi: true,
      scrollback: 10000,
      convertEol: false,
      macOptionIsMeta: true,
      rightClickSelectsWord: true,
      minimumContrastRatio: 1,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(hostRef.current);
    try {
      const webgl = new WebglAddon();
      webgl.onContextLoss(() => webgl.dispose());
      term.loadAddon(webgl);
    } catch (e) {
      console.warn("WebGL renderer unavailable, falling back:", e);
    }
    try {
      fit.fit();
    } catch {}

    termRef.current = term;
    fitRef.current = fit;

    const markWaiting = () => {
      setShellStatus(shell.id, "waiting");
      if (useAppStore.getState().activeShellId !== shell.id) {
        setShellUnread(shell.id, true);
      }
    };

    // OSC 7 — cwd updates from shell
    term.parser.registerOscHandler(7, (payload) => {
      // format: file://hostname/absolute/path
      try {
        const m = /^file:\/\/[^/]*(\/.+)$/.exec(payload);
        if (m) {
          let p = decodeURIComponent(m[1]);
          // On Windows paths come as /C:/Users/... — strip leading slash
          if (/^\/[a-zA-Z]:/.test(p)) p = p.slice(1).replace(/\//g, "\\");
          setShellCwd(shell.id, p);
        }
      } catch {}
      return false;
    });

    // OSC 9 — typical "bell" / notification
    term.parser.registerOscHandler(9, () => {
      markWaiting();
      return false;
    });
    const onBell = term.onBell(() => {
      markWaiting();
    });

    let unlistenData: UnlistenFn | null = null;
    let unlistenExit: UnlistenFn | null = null;

    const writeChunk = (e: PtyDataEvent) => {
      attachedSeqRef.current = e.seq;
      const bytes = base64ToBytes(e.data);
      term.write(bytes);
      if (useAppStore.getState().shells[shell.id]?.status !== "waiting") {
        setShellStatus(shell.id, "running");
      }
      if (useAppStore.getState().activeShellId !== shell.id) {
        setShellUnread(shell.id, true);
      }
    };

    const init = async () => {
      unlistenData = await onPtyData((e) => {
        if (e.sessionId !== sessionIdRef.current) return;
        if (!attachCompleteRef.current) {
          pendingDataRef.current.push(e);
          return;
        }
        if (e.seq <= attachedSeqRef.current) {
          return;
        }
        writeChunk(e);
      });
      unlistenExit = await onPtyExit((e) => {
        if (e.sessionId !== sessionIdRef.current) return;
        setShellExit(shell.id, e.code);
        sessionIdRef.current = null;
        attachedSeqRef.current = 0;
        attachCompleteRef.current = false;
        pendingDataRef.current = [];
      });

      const rows = term.rows;
      const cols = term.cols;
      let sid = sessionIdRef.current;
      if (!sid) {
        const projectPath =
          useAppStore.getState().projects[shell.projectId]?.path ?? shell.cwd;
        let spawnCwd = shell.cwd;
        if (!(await pathExists(spawnCwd)) && projectPath !== spawnCwd) {
          spawnCwd = projectPath;
          setShellCwd(shell.id, projectPath);
        }

        sid = await ptySpawn(shell.projectId, spawnCwd, rows, cols);
        sessionIdRef.current = sid;
        if (!disposedRef.current) setShellSession(shell.id, sid);
      } else {
        // ensure backend size matches
        ptyResize(sid, rows, cols).catch(() => {});
      }
      setShellSize(shell.id, cols, rows);

      const snapshot = await ptyAttach(sid);
      if (disposedRef.current || sessionIdRef.current !== sid) return;

      attachedSeqRef.current = snapshot.lastSeq;
      if (snapshot.data) {
        const bytes = base64ToBytes(snapshot.data);
        term.write(bytes);
        setShellStatus(shell.id, "running");
        if (useAppStore.getState().activeShellId !== shell.id) {
          setShellUnread(shell.id, true);
        }
      }

      attachCompleteRef.current = true;

      const pending = pendingDataRef.current
        .filter((e) => e.seq > attachedSeqRef.current)
        .sort((a, b) => a.seq - b.seq);
      pendingDataRef.current = [];
      for (const e of pending) {
        writeChunk(e);
      }
    };
    init().catch((e) => {
      const message = e instanceof Error ? e.message : String(e);
      setShellStatus(shell.id, "error");
      term.writeln("[SideShell] Failed to start shell.");
      term.writeln(message);
      console.error("init terminal failed", e);
    });

    const onInput = term.onData((data) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      if (useAppStore.getState().shells[shell.id]?.status === "waiting") {
        setShellStatus(shell.id, "running");
      }
      ptyWrite(sid, stringToBase64(data)).catch(() => {});
    });

    // Transition to idle after a short quiet period
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    const quietHandler = term.onWriteParsed(() => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        if (useAppStore.getState().shells[shell.id]?.status === "running") {
          setShellStatus(shell.id, "idle");
        }
      }, 400);
    });

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (!fitRef.current || !termRef.current) return;
      try {
        fitRef.current.fit();
      } catch {}
      const sid = sessionIdRef.current;
      if (sid) {
        ptyResize(sid, termRef.current.rows, termRef.current.cols).catch(
          () => {}
        );
      }
      setShellSize(shell.id, termRef.current.cols, termRef.current.rows);
    });
    ro.observe(hostRef.current);

    return () => {
      disposedRef.current = true;
      if (idleTimer) clearTimeout(idleTimer);
      ro.disconnect();
      quietHandler.dispose();
      onBell.dispose();
      onInput.dispose();
      unlistenData?.();
      unlistenExit?.();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.id]);

  // Re-fit + focus when becoming active
  useEffect(() => {
    if (!active) return;
    requestAnimationFrame(() => {
      try {
        fitRef.current?.fit();
        termRef.current?.focus();
      } catch {}
      const t = termRef.current;
      const sid = sessionIdRef.current;
      if (t && sid) {
        ptyResize(sid, t.rows, t.cols).catch(() => {});
      }
    });
    if (shell.hasUnread) setShellUnread(shell.id, false);
  }, [active, shell.id, shell.hasUnread, setShellUnread]);

  return (
    <div
      className="absolute inset-0 px-2.5 pt-2 pb-2"
      style={{
        visibility: active ? "visible" : "hidden",
        zIndex: active ? 10 : 0,
        pointerEvents: active ? "auto" : "none",
      }}
    >
      <div ref={hostRef} className="w-full h-full" />
    </div>
  );
}
