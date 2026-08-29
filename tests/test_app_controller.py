"""Qt-controller checks that do not require a working OpenGL display server."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


try:
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True

if PYSIDE6_AVAILABLE:
    VISUALIZER_DIR = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(VISUALIZER_DIR))
    from app import (  # noqa: E402
        ANIMATION_DURATION_MS,
        CubeVisualizerWindow,
        solver_program_problem,
    )
    from cube_view import configure_opengl_surface_format  # noqa: E402
    from cube_model import CubeState, apply_move, format_course_input, parse_course_input  # noqa: E402
    from solver_runner import SolverResult, SolverStatus  # noqa: E402


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not installed")
class AppControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configure_opengl_surface_format()
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = CubeVisualizerWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def _success(self, actions: tuple[str, ...]) -> "SolverResult":
        return SolverResult(
            status=SolverStatus.SUCCESS,
            actions=actions,
            stdout=(" ".join(actions) + "\n").encode("utf-8") if actions else b"",
            stderr=b"diagnostic\n",
            message="solver 已完成。",
            exit_code=0,
            elapsed_ms=12,
        )

    def test_solver_source_file_is_rejected_with_compile_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ms-Astar.cpp"
            source.write_text("int main() {}\n", encoding="utf-8")

            problem = solver_program_problem(source)

        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("C++ 源文件", problem)
        self.assertIn("clang++ -std=c++17 -O2", problem)
        self.assertIn("ms-Astar", problem)

    def test_foreign_executables_are_explained_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            linux_program = Path(directory) / "linux-solver"
            linux_program.write_bytes(b"\x7fELF" + b"unused")
            windows_program = Path(directory) / "solver.exe"
            windows_program.write_bytes(b"MZ" + b"unused")

            linux_problem = solver_program_problem(linux_program, host_platform="darwin")
            windows_problem = solver_program_problem(windows_program, host_platform="darwin")
            windows_ok = solver_program_problem(windows_program, host_platform="win32")

        self.assertIn("Linux ELF", linux_problem or "")
        self.assertIn("Windows .exe", windows_problem or "")
        self.assertIsNone(windows_ok)

    def test_core_profile_is_global_before_qapplication(self) -> None:
        surface_format = QSurfaceFormat.defaultFormat()
        self.assertEqual((surface_format.majorVersion(), surface_format.minorVersion()), (3, 2))
        self.assertEqual(
            surface_format.profile(),
            QSurfaceFormat.OpenGLContextProfile.CoreProfile,
        )
        self.assertGreaterEqual(surface_format.depthBufferSize(), 24)

    def test_slider_jumps_to_precomputed_state_and_pauses_animation(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        self.window._pending_initial = initial
        self.window._on_solver_completed(self._success(("0+", "6-", "8+")))
        self.assertTrue(self.window._animating)

        self.window._seek_step(2)
        session = self.window.session
        assert session is not None
        self.assertFalse(self.window._animating)
        self.assertFalse(session.replay.playing)
        self.assertEqual(session.replay.index, 2)
        self.assertEqual(self.window.cube_view.state, session.replay.states[2])
        self.assertEqual(self.window.progress_slider.value(), 2)

        self.window._seek_step(3)
        self.assertTrue(session.replay.completed)
        self.assertIn("否", self.window.final_label.text())

    def test_animation_commits_exact_precomputed_next_state(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        self.window._pending_initial = initial
        self.window._on_solver_completed(self._success(("0+",)))
        QTest.qWait(ANIMATION_DURATION_MS + 100)

        session = self.window.session
        assert session is not None
        self.assertFalse(self.window._animating)
        self.assertTrue(session.replay.completed)
        self.assertEqual(self.window.cube_view.state, session.replay.states[-1])
        self.assertIn("否", self.window.final_label.text())

    def test_pause_then_continue_finishes_the_precomputed_timeline(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        self.window._pending_initial = initial
        self.window._on_solver_completed(self._success(("0+", "6-")))
        self.assertTrue(self.window._animating)

        self.window._toggle_playback()
        session = self.window.session
        assert session is not None
        self.assertFalse(self.window._animating)
        self.assertFalse(session.replay.playing)
        self.assertEqual(self.window.cube_view.state, initial)

        self.window._toggle_playback()
        QTest.qWait(2 * ANIMATION_DURATION_MS + 350)
        self.assertTrue(session.replay.completed)
        self.assertEqual(self.window.cube_view.state, session.replay.states[-1])

    def test_empty_output_for_unsolved_initial_is_not_made_playable(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        # One move makes a legal but unsolved state.
        from cube_model import apply_move

        self.window._pending_initial = apply_move(initial, "0+")
        self.window._on_solver_completed(self._success(()))
        self.assertIsNone(self.window.session)
        self.assertIn("为空", self.window.status_label.text())

    def test_manual_actions_use_the_current_discrete_state_and_course_mapping(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        self.window._restore_state = initial
        self.window.cube_view.set_state(apply_move(initial, "0+"))
        self.window.manual_actions_input.setText("6- 4+")

        self.window._run_manual_actions()

        session = self.window.session
        assert session is not None
        self.assertEqual(session.initial, apply_move(initial, "0+"))
        self.assertEqual(session.actions, ("6-", "4+"))
        self.assertEqual(session.replay.states[-1], apply_move(apply_move(session.initial, "6-"), "4+"))
        self.assertTrue(self.window._animating)

    def test_restore_and_copy_use_the_canonical_course_input_orientation(self) -> None:
        initial = CubeState.solved(("y", "r", "g", "p", "w", "b"))
        moved = apply_move(initial, "8-")
        self.window._restore_state = initial
        self.window.cube_view.set_state(moved)

        self.window._copy_current_state()
        self.assertEqual(parse_course_input(QApplication.clipboard().text()), moved)

        self.window._restore_initial_state()
        self.assertEqual(self.window.cube_view.state, initial)
        self.assertIsNone(self.window.session)


if __name__ == "__main__":
    unittest.main()
