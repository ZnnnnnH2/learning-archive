import { useEffect, useLayoutEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import type { UnlistenFn } from "@tauri-apps/api/event";
import {
  buildAgentRestoreCommand,
  consumeTypedInputBuffer,
  detectAgentLaunchFromCommand,
  normalizeFirstMessagePreview,
} from "../autoName";
import {
  createBellNotification,
  detectShellStatusFromOsc133,
  detectShellStatusFromTitle,
  parseOsc9Notification,
} from "../shellSignals";
import {
  ptyAttach,
  onPtyData,
  onPtyExit,
  pathExists,
  type PtyDataEvent,
  ptyResize,
  resolveAgentRestoreTarget,
  ptySpawn,
  ptyWrite,
} from "../ipc";
import {
  buildPtySpawnOptions,
  DEFAULT_TERMINAL_FONT_FAMILY,
} from "../terminalConfig";
import { dismissShellAlert, raiseShellAlert } from "../shellAlerts";
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
  const pendingResumeCommandRef = useRef<string | null>(null);
  const pendingCommandKindRef = useRef<"restore" | "startup" | null>(null);
  const promptReadyRef = useRef(false);
  const resumeSentRef = useRef(false);
  const resumeFallbackTimerRef = useRef<number | null>(null);
  const restoreResolveTimerRef = useRef<number | null>(null);
  const disposedRef = useRef(false);
  const typedInputRef = useRef("");
  const terminalFontFamily = useAppStore(
    (s) => s.terminalSettings.fontFamily
  );

  // Store getters (avoid re-subscribing on every change)
  const setShellSession = useAppStore((s) => s.setShellSession);
  const setShellStatus = useAppStore((s) => s.setShellStatus);
  const setShellAttention = useAppStore((s) => s.setShellAttention);
  const startShellAgentSession = useAppStore((s) => s.startShellAgentSession);
  const setShellRestoreTarget = useAppStore((s) => s.setShellRestoreTarget);
  const markShellRestoreResolveFailed = useAppStore(
    (s) => s.markShellRestoreResolveFailed
  );
  const clearShellRestorePending = useAppStore(
    (s) => s.clearShellRestorePending
  );
  const clearShellStartupCommand = useAppStore(
    (s) => s.clearShellStartupCommand
  );
  const setShellTerminalTitle = useAppStore((s) => s.setShellTerminalTitle);
  const setShellFirstMessagePreview = useAppStore(
    (s) => s.setShellFirstMessagePreview
  );
  const setShellCwd = useAppStore((s) => s.setShellCwd);
  const setShellSize = useAppStore((s) => s.setShellSize);
  const setShellExit = useAppStore((s) => s.setShellExit);

  const clearResumeFallbackTimer = () => {
    if (resumeFallbackTimerRef.current !== null) {
      window.clearTimeout(resumeFallbackTimerRef.current);
      resumeFallbackTimerRef.current = null;
    }
  };

  const clearRestoreResolveTimer = () => {
    if (restoreResolveTimerRef.current !== null) {
      window.clearTimeout(restoreResolveTimerRef.current);
      restoreResolveTimerRef.current = null;
    }
  };

  const updatePendingResumeCommand = (
    currentShell: Shell | null | undefined
  ): string | null => {
    let command: string | null = null;
    let kind: "restore" | "startup" | null = null;
    if (currentShell?.startupCommand) {
      command = currentShell.startupCommand;
      kind = "startup";
    } else if (
      currentShell?.restorePending &&
      !currentShell.restoreResolvePending
    ) {
      command = buildAgentRestoreCommand({
        kind: currentShell.agentKind,
        restoreCommandPrefix: currentShell.restoreCommandPrefix,
        restoreCommandSuffix: currentShell.restoreCommandSuffix,
        restoreFallbackCommand: currentShell.restoreFallbackCommand,
        restoreTarget: currentShell.restoreTarget,
      });
      kind = command ? "restore" : null;
    }
    pendingResumeCommandRef.current = command;
    pendingCommandKindRef.current = kind;
    if (!command) {
      clearResumeFallbackTimer();
    }
    return command;
  };

  const flushPendingResume = (force = false) => {
    const command = pendingResumeCommandRef.current;
    const sid = sessionIdRef.current;
    if (!command || !sid || resumeSentRef.current) return;
    if (!force && (!attachCompleteRef.current || !promptReadyRef.current)) {
      return;
    }

    const commandKind = pendingCommandKindRef.current;
    resumeSentRef.current = true;
    pendingResumeCommandRef.current = null;
    pendingCommandKindRef.current = null;
    clearResumeFallbackTimer();
    if (commandKind === "startup") {
      clearShellStartupCommand(shell.id);
    } else {
      clearShellRestorePending(shell.id);
    }
    setShellStatus(shell.id, "running");
    ptyWrite(sid, stringToBase64(`${command}\r`)).catch((error) => {
      resumeSentRef.current = false;
      pendingResumeCommandRef.current = command;
      pendingCommandKindRef.current = commandKind;
      setShellStatus(shell.id, "error");
      console.error("resume command failed", error);
    });
  };

  const scheduleResumeFallback = () => {
    if (
      !pendingResumeCommandRef.current ||
      resumeFallbackTimerRef.current !== null
    ) {
      return;
    }
    resumeFallbackTimerRef.current = window.setTimeout(() => {
      resumeFallbackTimerRef.current = null;
      flushPendingResume(true);
    }, 900);
  };

  const resolveRestoreTarget = async (
    currentShell: Shell,
    markFailure: boolean
  ): Promise<boolean> => {
    if (
      !currentShell.agentKind ||
      !currentShell.restoreResolvePending ||
      !currentShell.restoreResolveStrategy
    ) {
      return false;
    }

    try {
      const result = await resolveAgentRestoreTarget({
        agentKind: currentShell.agentKind,
        strategy: currentShell.restoreResolveStrategy,
        cwd: currentShell.restoreLaunchCwd ?? currentShell.cwd,
        launchStartedAt: currentShell.restoreLaunchStartedAt,
      });
      if (result?.target) {
        setShellRestoreTarget(
          currentShell.id,
          result.target,
          currentShell.restoreLaunchStartedAt
        );
        return true;
      }
    } catch (error) {
      console.error("resolve restore target failed", error);
    }

    if (markFailure) {
      markShellRestoreResolveFailed(
        currentShell.id,
        currentShell.restoreLaunchStartedAt
      );
    }
    return false;
  };

  // Mount xterm once per shell id
  useLayoutEffect(() => {
    if (!hostRef.current) return;
    disposedRef.current = false;
    attachedSeqRef.current = 0;
    attachCompleteRef.current = false;
    pendingDataRef.current = [];
    pendingResumeCommandRef.current = null;
    pendingCommandKindRef.current = null;
    promptReadyRef.current = false;
    resumeSentRef.current = false;
    clearResumeFallbackTimer();
    clearRestoreResolveTimer();
    typedInputRef.current = "";

    const term = new Terminal({
      fontFamily: terminalFontFamily || DEFAULT_TERMINAL_FONT_FAMILY,
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

    const markAttention = () => {
      raiseShellAlert(shell.id, createBellNotification());
    };
    const applyAgentLaunch = (line: string) => {
      const currentShell = useAppStore.getState().shells[shell.id];
      const launch = detectAgentLaunchFromCommand(
        line,
        currentShell?.cwd ?? shell.cwd
      );
      if (!launch) return false;
      startShellAgentSession(shell.id, launch, Date.now());
      return true;
    };
    const captureFirstMessagePreview = (line: string) => {
      const preview = normalizeFirstMessagePreview(line);
      const currentShell = useAppStore.getState().shells[shell.id];
      if (
        !preview ||
        !currentShell?.agentLabel ||
        currentShell.firstMessagePreview
      ) {
        return;
      }
      setShellFirstMessagePreview(shell.id, preview);
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
    term.parser.registerOscHandler(9, (payload) => {
      raiseShellAlert(shell.id, parseOsc9Notification(payload));
      return false;
    });
    const onBell = term.onBell(() => {
      markAttention();
    });
    const onTitleChange = term.onTitleChange((title) => {
      const currentShell = useAppStore.getState().shells[shell.id];
      setShellTerminalTitle(shell.id, title);
      const nextStatus = detectShellStatusFromTitle(title);
      if (nextStatus) {
        setShellStatus(shell.id, nextStatus);
        return;
      }
      if (currentShell?.agentKind === "codex" && title.trim()) {
        setShellStatus(shell.id, "idle");
      }
    });
    term.parser.registerOscHandler(133, (payload) => {
      if (payload.startsWith("B")) {
        promptReadyRef.current = true;
        flushPendingResume();
      }
      const currentStatus =
        useAppStore.getState().shells[shell.id]?.status ?? "idle";
      const nextStatus = detectShellStatusFromOsc133(payload, currentStatus);
      if (nextStatus) {
        setShellStatus(shell.id, nextStatus);
      }
      return false;
    });

    let unlistenData: UnlistenFn | null = null;
    let unlistenExit: UnlistenFn | null = null;

    const writeChunk = (e: PtyDataEvent) => {
      attachedSeqRef.current = e.seq;
      const bytes = base64ToBytes(e.data);
      term.write(bytes);
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

        const spawnOptions = buildPtySpawnOptions(
          useAppStore.getState().terminalSettings
        );
        sid = await ptySpawn(
          shell.projectId,
          spawnCwd,
          rows,
          cols,
          spawnOptions
        );
        sessionIdRef.current = sid;
        if (!disposedRef.current) setShellSession(shell.id, sid);
      } else if (useAppStore.getState().activeShellId === shell.id) {
        // ensure backend size matches
        ptyResize(sid, rows, cols).catch(() => {});
      }
      setShellSize(shell.id, cols, rows);

      let currentShell = useAppStore.getState().shells[shell.id];
      if (currentShell?.restoreResolvePending) {
        await resolveRestoreTarget(currentShell, true);
        currentShell = useAppStore.getState().shells[shell.id];
      }
      updatePendingResumeCommand(currentShell);

      const snapshot = await ptyAttach(sid);
      if (disposedRef.current || sessionIdRef.current !== sid) return;

      attachedSeqRef.current = snapshot.lastSeq;
      if (snapshot.data) {
        const bytes = base64ToBytes(snapshot.data);
        term.write(bytes);
      }

      attachCompleteRef.current = true;
      flushPendingResume();
      scheduleResumeFallback();

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
      const consumed = consumeTypedInputBuffer(typedInputRef.current, data);
      typedInputRef.current = consumed.line;
      for (const line of consumed.submittedLines) {
        if (applyAgentLaunch(line)) continue;
        captureFirstMessagePreview(line);
      }
      ptyWrite(sid, stringToBase64(data)).catch(() => {});
    });

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (!fitRef.current || !termRef.current) return;
      if (useAppStore.getState().activeShellId !== shell.id) return;
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
      ro.disconnect();
      onBell.dispose();
      onTitleChange.dispose();
      onInput.dispose();
      unlistenData?.();
      unlistenExit?.();
      clearResumeFallbackTimer();
      clearRestoreResolveTimer();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell.id]);

  useEffect(() => {
    if (!termRef.current) return;
    termRef.current.options.fontFamily =
      terminalFontFamily || DEFAULT_TERMINAL_FONT_FAMILY;
    requestAnimationFrame(() => {
      try {
        fitRef.current?.fit();
      } catch {}
    });
  }, [terminalFontFamily]);

  useEffect(() => {
    updatePendingResumeCommand(shell);
    flushPendingResume();
    scheduleResumeFallback();
  }, [
    shell.id,
    shell.agentKind,
    shell.restorePending,
    shell.restoreResolvePending,
    shell.restoreCommandPrefix,
    shell.restoreCommandSuffix,
    shell.restoreFallbackCommand,
    shell.startupCommand,
    shell.restoreTarget?.kind,
    shell.restoreTarget?.value,
  ]);

  useEffect(() => {
    if (!shell.restoreResolvePending || shell.restorePending) {
      clearRestoreResolveTimer();
      return;
    }

    let cancelled = false;

    const run = async () => {
      const currentShell = useAppStore.getState().shells[shell.id];
      if (!currentShell?.restoreResolvePending || currentShell.restorePending) {
        clearRestoreResolveTimer();
        return;
      }

      const resolved = await resolveRestoreTarget(currentShell, false);
      if (cancelled) return;
      if (resolved) return;

      clearRestoreResolveTimer();
      restoreResolveTimerRef.current = window.setTimeout(() => {
        restoreResolveTimerRef.current = null;
        void run();
      }, 1500);
    };

    void run();

    return () => {
      cancelled = true;
      clearRestoreResolveTimer();
    };
  }, [
    shell.id,
    shell.restorePending,
    shell.restoreResolvePending,
    shell.restoreResolveStrategy,
    shell.restoreLaunchStartedAt,
    shell.restoreLaunchCwd,
    shell.cwd,
  ]);

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
        setShellSize(shell.id, t.cols, t.rows);
      }
    });
    dismissShellAlert(shell.id);
    if (shell.needsAttention) setShellAttention(shell.id, false);
  }, [active, shell.id, shell.needsAttention, setShellAttention, setShellSize]);

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
