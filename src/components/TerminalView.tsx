import { memo, useEffect, useLayoutEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import type { UnlistenFn } from "@tauri-apps/api/event";
import {
  consumeTypedInputBuffer,
  detectAgentLaunchFromCommand,
  summarizeAgentTaskFromInput,
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
  ptySpawn,
  ptyWrite,
} from "../ipc";
import {
  buildPtySpawnOptions,
  DEFAULT_TERMINAL_FONT_FAMILY,
} from "../terminalConfig";
import { matchShortcutAction } from "../shortcuts";
import { translate } from "../i18n";
import { dismissShellAlert, raiseShellAlert } from "../shellAlerts";
import { base64ToBytes, stringToBase64 } from "../utils";
import { useAppStore } from "../store";
import type { Shell, ShortcutKeymap } from "../types";

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

const TERMINAL_SCROLLBACK = 3000;
const TERMINAL_WRITE_FRAME_BYTES = 256 * 1024;

function TerminalViewComponent({ shell, active }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const sessionIdRef = useRef<string | null>(shell.sessionId);
  const attachedSeqRef = useRef(0);
  const attachCompleteRef = useRef(false);
  const pendingDataRef = useRef<PtyDataEvent[]>([]);
  const pendingResumeCommandRef = useRef<string | null>(null);
  const pendingCommandKindRef = useRef<"startup" | null>(null);
  const promptReadyRef = useRef(false);
  const resumeSentRef = useRef(false);
  const resumeFallbackTimerRef = useRef<number | null>(null);
  const writeFrameRef = useRef<number | null>(null);
  const queuedWriteChunksRef = useRef<Uint8Array[]>([]);
  const queuedWriteBytesRef = useRef(0);
  const disposedRef = useRef(false);
  const typedInputRef = useRef("");
  const shortcutKeymapRef = useRef<ShortcutKeymap>(
    useAppStore.getState().terminalSettings.shortcutKeymap
  );
  const terminalFontFamily = useAppStore(
    (s) => s.terminalSettings.fontFamily
  );
  const locale = useAppStore((s) => s.terminalSettings.locale);
  const shortcutKeymap = useAppStore((s) => s.terminalSettings.shortcutKeymap);

  // Store getters (avoid re-subscribing on every change)
  const setShellSession = useAppStore((s) => s.setShellSession);
  const setShellStatus = useAppStore((s) => s.setShellStatus);
  const setShellAttention = useAppStore((s) => s.setShellAttention);
  const startShellAgentSession = useAppStore((s) => s.startShellAgentSession);
  const clearShellStartupCommand = useAppStore(
    (s) => s.clearShellStartupCommand
  );
  const setShellTerminalTitle = useAppStore((s) => s.setShellTerminalTitle);
  const setShellTaskSummary = useAppStore((s) => s.setShellTaskSummary);
  const setShellCwd = useAppStore((s) => s.setShellCwd);
  const setShellSize = useAppStore((s) => s.setShellSize);
  const setShellExit = useAppStore((s) => s.setShellExit);

  const clearResumeFallbackTimer = () => {
    if (resumeFallbackTimerRef.current !== null) {
      window.clearTimeout(resumeFallbackTimerRef.current);
      resumeFallbackTimerRef.current = null;
    }
  };

  const clearQueuedTerminalWrites = () => {
    if (writeFrameRef.current !== null) {
      window.cancelAnimationFrame(writeFrameRef.current);
      writeFrameRef.current = null;
    }
    queuedWriteChunksRef.current = [];
    queuedWriteBytesRef.current = 0;
  };

  const trackAgentLaunch = (line: string) => {
    const currentShell = useAppStore.getState().shells[shell.id];
    const launch = detectAgentLaunchFromCommand(
      line,
      currentShell?.cwd ?? shell.cwd
    );
    if (!launch) return false;
    startShellAgentSession(shell.id, launch);
    return true;
  };

  const updatePendingResumeCommand = (
    currentShell: Shell | null | undefined
  ): string | null => {
    let command: string | null = null;
    let kind: "startup" | null = null;
    if (currentShell?.startupCommand) {
      command = currentShell.startupCommand;
      kind = "startup";
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
    trackAgentLaunch(command);
    resumeSentRef.current = true;
    pendingResumeCommandRef.current = null;
    pendingCommandKindRef.current = null;
    clearResumeFallbackTimer();
    if (commandKind === "startup") {
      clearShellStartupCommand(shell.id);
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

  useEffect(() => {
    shortcutKeymapRef.current = shortcutKeymap;
  }, [shortcutKeymap]);

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
    clearQueuedTerminalWrites();
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
      scrollback: TERMINAL_SCROLLBACK,
      convertEol: false,
      macOptionIsMeta: true,
      rightClickSelectsWord: true,
      minimumContrastRatio: 1,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.attachCustomKeyEventHandler((event) =>
      handleTerminalShortcut(term, shortcutKeymapRef.current, event)
    );
    term.open(hostRef.current);
    try {
      fit.fit();
    } catch {}

    termRef.current = term;
    fitRef.current = fit;

    const markAttention = () => {
      raiseShellAlert(shell.id, createBellNotification());
    };
    const captureTaskSummary = (line: string) => {
      const currentShell = useAppStore.getState().shells[shell.id];
      const summary = summarizeAgentTaskFromInput(line);
      if (
        !summary ||
        !currentShell?.agentLabel ||
        currentShell.taskSummary === summary
      ) {
        return;
      }
      setShellTaskSummary(shell.id, summary);
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

    const flushTerminalWrites = () => {
      writeFrameRef.current = null;
      if (disposedRef.current || !termRef.current) {
        clearQueuedTerminalWrites();
        return;
      }

      const chunks = queuedWriteChunksRef.current;
      if (chunks.length === 0) {
        queuedWriteBytesRef.current = 0;
        return;
      }

      let bytesToWrite: Uint8Array;
      if (chunks.length === 1) {
        bytesToWrite = chunks.shift()!;
        queuedWriteBytesRef.current = 0;
      } else {
        const totalBytes = queuedWriteBytesRef.current;
        bytesToWrite = new Uint8Array(totalBytes);
        let offset = 0;
        for (const chunk of chunks) {
          bytesToWrite.set(chunk, offset);
          offset += chunk.length;
        }
        queuedWriteChunksRef.current = [];
        queuedWriteBytesRef.current = 0;
      }

      term.write(bytesToWrite);
    };

    const scheduleTerminalWrite = (bytes: Uint8Array) => {
      if (bytes.length === 0) return;
      queuedWriteChunksRef.current.push(bytes);
      queuedWriteBytesRef.current += bytes.length;
      if (queuedWriteBytesRef.current >= TERMINAL_WRITE_FRAME_BYTES) {
        if (writeFrameRef.current !== null) {
          window.cancelAnimationFrame(writeFrameRef.current);
          writeFrameRef.current = null;
        }
        flushTerminalWrites();
        return;
      }
      if (writeFrameRef.current === null) {
        writeFrameRef.current = window.requestAnimationFrame(flushTerminalWrites);
      }
    };

    const writeChunk = (e: PtyDataEvent) => {
      attachedSeqRef.current = e.seq;
      scheduleTerminalWrite(base64ToBytes(e.data));
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
      updatePendingResumeCommand(useAppStore.getState().shells[shell.id]);

      const snapshot = await ptyAttach(sid);
      if (disposedRef.current || sessionIdRef.current !== sid) return;

      attachedSeqRef.current = snapshot.lastSeq;
      if (snapshot.data) {
        scheduleTerminalWrite(base64ToBytes(snapshot.data));
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
      term.writeln(translate(locale, "terminal.startFailed"));
      term.writeln(message);
      console.error("init terminal failed", e);
    });

    const onInput = term.onData((data) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      const consumed = consumeTypedInputBuffer(typedInputRef.current, data);
      typedInputRef.current = consumed.line;
      for (const line of consumed.submittedLines) {
        if (trackAgentLaunch(line)) continue;
        captureTaskSummary(line);
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
      clearQueuedTerminalWrites();
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
    shell.startupCommand,
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
      <div ref={hostRef} className="xterm-host w-full h-full" />
    </div>
  );
}

export const TerminalView = memo(TerminalViewComponent);

function handleTerminalShortcut(
  term: Terminal,
  shortcutKeymap: ShortcutKeymap,
  event: KeyboardEvent
): boolean {
  const actionId = matchShortcutAction(shortcutKeymap, event, "terminal");
  if (!actionId) return true;

  event.preventDefault();
  event.stopPropagation();

  if (actionId === "terminal.copySelection") {
    const selection = term.hasSelection() ? term.getSelection() : "";
    if (selection && navigator.clipboard) {
      void navigator.clipboard.writeText(selection).catch((error) => {
        console.warn("terminal copy failed", error);
      });
    }
    return false;
  }

  if (actionId === "terminal.pasteClipboard") {
    if (navigator.clipboard) {
      void navigator.clipboard
        .readText()
        .then((text) => {
          if (text) term.paste(text);
        })
        .catch((error) => {
          console.warn("terminal paste failed", error);
        });
    }
    return false;
  }

  return true;
}
