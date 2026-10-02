"""Black-box QProcess tests for the solver runner."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import textwrap
import unittest


try:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
except ImportError:  # Keep the pure-model test suite runnable without Qt.
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True

if PYSIDE6_AVAILABLE:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from solver_runner import (  # noqa: E402
        DEFAULT_TIMEOUT_MS,
        SolverRunner,
        SolverStatus,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not installed")
class SolverRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _solver_script(self, body: str) -> Path:
        path = Path(self.temporary_directory.name) / "solver.py"
        path.write_text(
            f"#!{sys.executable}\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _run(
        self,
        runner: "SolverRunner",
        program: Path,
        stdin_bytes: bytes = b"",
        *,
        stdin_text: str | None = None,
        timeout_ms: int = 1_000,
        cancel_after_ms: int | None = None,
    ) -> tuple[object, list[object], list[str]]:
        results: list[object] = []
        failures: list[object] = []
        started: list[str] = []
        loop = QEventLoop()
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(loop.quit)
        runner.completed.connect(lambda result: (results.append(result), loop.quit()))
        runner.failed.connect(failures.append)
        runner.started.connect(started.append)
        if stdin_text is None:
            runner.run_bytes(str(program), stdin_bytes, timeout_ms)
        else:
            runner.run(str(program), stdin_text, timeout_ms)
        if cancel_after_ms is not None:
            QTimer.singleShot(cancel_after_ms, runner.cancel)
        guard.start(timeout_ms + 2_000)
        if not results:
            loop.exec()
        guard.stop()
        self.assertTrue(results, "runner did not complete before test guard timeout")
        return results[0], failures, started

    def test_success_parses_actions_preserves_raw_input_and_keeps_stderr(self) -> None:
        payload = b"\x00cube request\n"
        solver = self._solver_script(
            f"""
            import sys
            payload = sys.stdin.buffer.read()
            if payload != {payload!r}:
                sys.stderr.write("unexpected stdin")
                raise SystemExit(9)
            sys.stdout.write("0+ 6- 8+\\n")
            sys.stderr.write("diagnostic\\n")
            """
        )

        result, failures, started = self._run(SolverRunner(), solver, payload)

        self.assertEqual(result.status, SolverStatus.SUCCESS)
        self.assertTrue(result.ok)
        self.assertEqual(result.actions, ("0+", "6-", "8+"))
        self.assertEqual(result.stderr, b"diagnostic\n")
        self.assertEqual(failures, [])
        self.assertEqual(started, [str(solver)])

    def test_text_api_encodes_utf8_before_writing_stdin(self) -> None:
        request = "魔方\n"
        solver = self._solver_script(
            f"""
            import sys
            if sys.stdin.buffer.read() != {request.encode('utf-8')!r}:
                raise SystemExit(9)
            print('0+')
            """
        )

        result, _, _ = self._run(
            SolverRunner(), solver, stdin_text=request
        )
        self.assertEqual(result.status, SolverStatus.SUCCESS)
        self.assertEqual(result.actions, ("0+",))

    def test_nonzero_exit_is_reported_and_emits_failed(self) -> None:
        solver = self._solver_script(
            """
            import sys
            sys.stderr.write("solver failed\\n")
            raise SystemExit(7)
            """
        )

        result, failures, _ = self._run(SolverRunner(), solver)

        self.assertEqual(result.status, SolverStatus.NONZERO_EXIT)
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.stderr, b"solver failed\n")
        self.assertEqual(failures, [result])

    def test_crashed_solver_is_reported_separately_from_a_nonzero_exit(self) -> None:
        solver = self._solver_script(
            """
            import os
            import signal
            os.kill(os.getpid(), signal.SIGKILL)
            """
        )

        result, failures, _ = self._run(SolverRunner(), solver)

        self.assertEqual(result.status, SolverStatus.CRASHED)
        self.assertEqual(failures, [result])

    def test_invalid_action_output_is_reported(self) -> None:
        solver = self._solver_script("print('debug line')")

        result, failures, _ = self._run(SolverRunner(), solver)

        self.assertEqual(result.status, SolverStatus.BAD_OUTPUT)
        self.assertIn("无效", result.message)
        self.assertEqual(failures, [result])

    def test_nonempty_action_output_must_end_with_a_newline(self) -> None:
        unterminated_solver = self._solver_script(
            """
            import sys
            sys.stdout.write('0+')
            """
        )
        result, _, _ = self._run(SolverRunner(), unterminated_solver)
        self.assertEqual(result.status, SolverStatus.BAD_OUTPUT)
        self.assertIn("换行", result.message)

        empty_solver = self._solver_script("pass")
        empty_result, _, _ = self._run(SolverRunner(), empty_solver)
        self.assertEqual(empty_result.status, SolverStatus.SUCCESS)
        self.assertEqual(empty_result.actions, ())

    def test_timeout_and_cancellation_are_distinct(self) -> None:
        solver = self._solver_script(
            """
            import time
            time.sleep(5)
            """
        )

        timed_out, _, _ = self._run(SolverRunner(), solver, timeout_ms=40)
        self.assertEqual(timed_out.status, SolverStatus.TIMED_OUT)

        cancelled, _, _ = self._run(
            SolverRunner(), solver, timeout_ms=1_000, cancel_after_ms=20
        )
        self.assertEqual(cancelled.status, SolverStatus.CANCELLED)

    def test_output_cap_applies_to_each_stream(self) -> None:
        stdout_solver = self._solver_script(
            """
            import sys
            sys.stdout.buffer.write(b'x' * 80)
            """
        )
        stdout_result, _, _ = self._run(
            SolverRunner(output_limit_bytes=64), stdout_solver
        )
        self.assertEqual(stdout_result.status, SolverStatus.OUTPUT_LIMIT_EXCEEDED)
        self.assertEqual(len(stdout_result.stdout), 64)

        stderr_solver = self._solver_script(
            """
            import sys
            sys.stderr.buffer.write(b'x' * 80)
            """
        )
        stderr_result, _, _ = self._run(
            SolverRunner(output_limit_bytes=64), stderr_solver
        )
        self.assertEqual(stderr_result.status, SolverStatus.OUTPUT_LIMIT_EXCEEDED)
        self.assertEqual(len(stderr_result.stderr), 64)

    def test_documented_default_timeout_is_five_minutes(self) -> None:
        self.assertEqual(DEFAULT_TIMEOUT_MS, 5 * 60 * 1_000)


if __name__ == "__main__":
    unittest.main()
