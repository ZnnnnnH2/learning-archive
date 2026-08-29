"""Asynchronous, shell-free runner for a cube solver executable.

The GUI owns one :class:`SolverRunner` and starts it with a serialized cube
request.  The runner never gives the solver a shell; it writes UTF-8 bytes to
``QProcess`` stdin and collects stdout/stderr on their independent channels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

try:  # Support both `python cube_gui.py` and package-style imports.
    from .cube_model import parse_action_output
except ImportError:  # pragma: no cover - exercised by direct script launch.
    from cube_model import parse_action_output


DEFAULT_TIMEOUT_MS = 5 * 60 * 1000
DEFAULT_OUTPUT_LIMIT_BYTES = 1 * 1024 * 1024


class SolverStatus(str, Enum):
    """Terminal outcomes emitted by :class:`SolverRunner`."""

    SUCCESS = "success"
    FAILED_TO_START = "failed_to_start"
    NONZERO_EXIT = "nonzero_exit"
    CRASHED = "crashed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    BAD_OUTPUT = "bad_output"
    PROCESS_ERROR = "process_error"


@dataclass(frozen=True)
class SolverResult:
    """The complete, immutable result of one solver invocation.

    ``stdout`` and ``stderr`` preserve the original byte streams separately.
    The text properties are only for display; action parsing always uses a
    strict UTF-8 decode of stdout before calling ``parse_action_output``.
    """

    status: SolverStatus
    actions: tuple[str, ...]
    stdout: bytes
    stderr: bytes
    message: str
    exit_code: int | None
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return self.status is SolverStatus.SUCCESS

    @property
    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


class SolverRunner(QObject):
    """Run one external cube solver at a time using ``QProcess``.

    Connect to ``completed`` for every terminal outcome and ``failed`` for a
    non-success outcome.  ``run`` is the GUI-facing convenience API; it
    encodes a request string once and delegates to ``run_bytes`` so stdin is
    always supplied to ``QProcess`` as raw bytes.  No command line is passed
    through a shell.
    """

    started = Signal(str)
    completed = Signal(object)
    failed = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> None:
        super().__init__(parent)
        if not isinstance(output_limit_bytes, int) or isinstance(output_limit_bytes, bool):
            raise TypeError("output_limit_bytes 必须是整数。")
        if output_limit_bytes <= 0:
            raise ValueError("output_limit_bytes 必须大于 0。")

        self._output_limit_bytes = output_limit_bytes
        self._process: QProcess | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

        self._stdout = bytearray()
        self._stderr = bytearray()
        self._input_bytes = b""
        self._started_at: float | None = None
        self._termination: tuple[SolverStatus, str] | None = None
        self._completed = False
        self._exit_code: int | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and not self._completed

    def run(
        self,
        program_path: str,
        stdin_text: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Start ``program_path`` with a UTF-8 text request.

        The program receives exactly ``stdin_text.encode('utf-8')`` through
        stdin, without shell expansion or implicit command-line parsing.
        Completion is reported asynchronously through the Qt signals.
        """
        if not isinstance(stdin_text, str):
            raise TypeError("stdin_text 必须是字符串。")
        self.run_bytes(program_path, stdin_text.encode("utf-8"), timeout_ms)

    def run_bytes(
        self,
        program_path: str,
        stdin_bytes: bytes | bytearray | memoryview,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Start a solver with raw stdin bytes.

        This lower-level variant is useful for protocol tests and preserves the
        bytes exactly as supplied.  It intentionally accepts no command line
        string or shell expression: ``program_path`` is the executable path.
        """
        if self.is_running:
            raise RuntimeError("已有 solver 正在运行；请先等待 completed 信号。")
        if not isinstance(program_path, str) or not program_path:
            raise ValueError("program_path 必须是非空字符串。")
        if not isinstance(stdin_bytes, (bytes, bytearray, memoryview)):
            raise TypeError("stdin_bytes 必须是 bytes、bytearray 或 memoryview。")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
            raise TypeError("timeout_ms 必须是整数。")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms 必须大于 0。")

        self._stdout.clear()
        self._stderr.clear()
        self._input_bytes = bytes(stdin_bytes)
        self._started_at = time.monotonic()
        self._termination = None
        self._completed = False
        self._exit_code = None

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.setProgram(program_path)
        process.setArguments([])
        process.started.connect(self._on_process_started)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        self._process = process

        # Start the deadline before launch so a pathological launch cannot run
        # beyond the same limit as a running solver.
        self._timer.start(timeout_ms)
        process.start()

    def cancel(self) -> bool:
        """Cancel the active run, returning whether there was one to cancel."""
        if not self.is_running:
            return False
        self._request_stop(SolverStatus.CANCELLED, "求解已由用户取消。")
        return True

    def _on_process_started(self) -> None:
        if self._completed or self._process is None:
            return
        if self._input_bytes:
            self._process.write(self._input_bytes)
        self._process.closeWriteChannel()
        self.started.emit(self._process.program())

    def _read_stdout(self) -> None:
        process = self._process
        if process is None:
            return
        self._append_output(bytes(process.readAllStandardOutput()), self._stdout, "stdout")

    def _read_stderr(self) -> None:
        process = self._process
        if process is None:
            return
        self._append_output(bytes(process.readAllStandardError()), self._stderr, "stderr")

    def _append_output(self, data: bytes, target: bytearray, channel: str) -> None:
        if not data:
            return
        available = max(0, self._output_limit_bytes - len(target))
        if available:
            target.extend(data[:available])
        if len(data) > available and self._termination is None:
            self._request_stop(
                SolverStatus.OUTPUT_LIMIT_EXCEEDED,
                f"solver 的 {channel} 超过 {self._output_limit_bytes} 字节上限。",
            )

    def _read_remaining_output(self) -> None:
        self._read_stdout()
        self._read_stderr()

    def _on_timeout(self) -> None:
        if self.is_running:
            self._request_stop(
                SolverStatus.TIMED_OUT,
                "solver 超过时限，已停止。",
            )

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if self._completed:
            return
        process = self._process
        if process is None:
            return
        if self._termination is not None:
            # An intentional kill commonly reports Crashed; final status stays
            # timeout/cancel/output-limit rather than becoming a crash.
            if process.state() == QProcess.ProcessState.NotRunning:
                status, message = self._termination
                self._complete(status, message)
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._complete(
                SolverStatus.FAILED_TO_START,
                f"无法启动 solver：{process.errorString()}",
            )
            return
        if error == QProcess.ProcessError.Crashed:
            self._complete(SolverStatus.CRASHED, "solver 异常崩溃。")
            return
        self._request_stop(
            SolverStatus.PROCESS_ERROR,
            f"solver 进程错误：{process.errorString()}",
        )

    def _on_process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        if self._completed:
            return
        self._exit_code = int(exit_code)
        self._read_remaining_output()

        if self._termination is not None:
            status, message = self._termination
            self._complete(status, message)
            return
        if exit_status == QProcess.ExitStatus.CrashExit:
            self._complete(SolverStatus.CRASHED, "solver 异常崩溃。")
            return
        if exit_code != 0:
            self._complete(SolverStatus.NONZERO_EXIT, f"solver 以退出码 {exit_code} 结束。")
            return

        try:
            stdout_text = bytes(self._stdout).decode("utf-8")
        except UnicodeDecodeError as error:
            self._complete(
                SolverStatus.BAD_OUTPUT,
                f"solver stdout 不是有效 UTF-8，无法解析动作：{error}。",
            )
            return
        try:
            actions = tuple(parse_action_output(stdout_text))
        except (TypeError, ValueError) as error:
            self._complete(SolverStatus.BAD_OUTPUT, f"solver 动作输出无效：{error}")
            return
        if actions and not stdout_text.endswith("\n"):
            self._complete(
                SolverStatus.BAD_OUTPUT,
                "solver 动作输出必须以换行结束。",
            )
            return
        self._complete(SolverStatus.SUCCESS, "solver 已完成。", actions=actions)

    def _request_stop(self, status: SolverStatus, message: str) -> None:
        if self._completed:
            return
        if self._termination is None:
            self._termination = (status, message)
        self._timer.stop()
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            final_status, final_message = self._termination
            self._complete(final_status, final_message)
            return
        process.kill()

    def _complete(
        self,
        status: SolverStatus,
        message: str,
        *,
        actions: tuple[str, ...] = (),
    ) -> None:
        if self._completed:
            return
        self._completed = True
        self._timer.stop()
        self._read_remaining_output()
        elapsed_ms = 0
        if self._started_at is not None:
            elapsed_ms = max(0, int((time.monotonic() - self._started_at) * 1000))
        result = SolverResult(
            status=status,
            actions=actions,
            stdout=bytes(self._stdout),
            stderr=bytes(self._stderr),
            message=message,
            exit_code=self._exit_code,
            elapsed_ms=elapsed_ms,
        )
        process = self._process
        self._process = None
        self._input_bytes = b""
        if process is not None:
            process.deleteLater()

        if not result.ok:
            self.failed.emit(result)
        self.completed.emit(result)
