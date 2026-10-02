"""Desktop entry point for the PySide6 three-dimensional cube visualizer.

The window is deliberately a visualizer and protocol checker, not a solver:
it sends the text in the input editor unchanged to one already-compiled
student executable, then animates the validated action stream it receives.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import os
from pathlib import Path
import shlex
import sys

from PySide6.QtCore import QElapsedTimer, QSignalBlocker, QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:  # Support both ``python app.py`` and ``python -m cube.visualizer.app``.
    from .cube_model import (
        CubeState,
        describe_move,
        format_course_input,
        is_goal,
        parse_course_input,
    )
    from .cube_view import CubeView, configure_opengl_surface_format
    from .replay import ReplaySession
    from .solver_runner import SolverResult, SolverRunner
except ImportError:  # pragma: no cover - direct launcher path.
    from cube_model import CubeState, describe_move, format_course_input, is_goal, parse_course_input
    from cube_view import CubeView, configure_opengl_surface_format
    from replay import ReplaySession
    from solver_runner import SolverResult, SolverRunner


SAMPLE_INPUT = """\
back:
g g r
r y r
y b y

down:
r r b
w r w
r r b

front:
w p w
g w g
b b p

left:
w w r
p g g
w y g

right:
p y y
b b b
b w y

up:
g y g
p p p
p y p
"""

ANIMATION_DURATION_MS = 280
ANIMATION_FRAME_MS = 16
CPP_SOURCE_SUFFIXES = frozenset({".c", ".cc", ".cpp", ".cxx", ".c++"})


def solver_program_problem(program: Path, *, host_platform: str | None = None) -> str | None:
    """Return a user-facing explanation when *program* cannot be launched.

    The visualizer deliberately executes an already-built solver rather than
    compiling untrusted student source.  Checking this before ``QProcess``
    starts turns macOS's opaque ``execve: Permission denied`` into an
    actionable explanation when a ``.cpp`` file was selected by mistake.
    """

    platform = sys.platform if host_platform is None else host_platform
    if not program.is_file():
        return f"找不到 solver 文件：{program}"
    if program.suffix.lower() in CPP_SOURCE_SUFFIXES:
        output = program.with_suffix("")
        return (
            f"你选择的是 C++ 源文件，不是可执行文件：{program.name}。"
            "请先在终端编译，例如：\n"
            f"clang++ -std=c++17 -O2 {shlex.quote(str(program))} "
            f"-o {shlex.quote(str(output))}\n"
            f"然后在这里选择生成的 {output.name}。"
        )
    try:
        with program.open("rb") as binary:
            header = binary.read(4)
    except OSError as error:
        return f"无法读取 solver 文件：{error}"
    if platform.startswith("darwin") and header == b"\x7fELF":
        return (
            f"{program.name} 是 Linux ELF 可执行文件，不能在 macOS 上运行。"
            "请在 macOS 上从同一份 C++ 源码重新编译。"
        )
    if platform.startswith("darwin") and header[:2] == b"MZ":
        return (
            f"{program.name} 是 Windows .exe 文件，不能在 macOS 上运行。"
            "请在 macOS 上从同一份 C++ 源码重新编译。"
        )
    if platform.startswith("win"):
        if program.suffix.lower() != ".exe":
            return "Windows 下请选择编译生成的 .exe solver 文件。"
        return None
    if not os.access(program, os.X_OK):
        return (
            f"solver 文件没有可执行权限：{program.name}。"
            f"请先执行：chmod +x {shlex.quote(str(program))}"
        )
    return None


@dataclass(frozen=True)
class VisualizerSession:
    """Everything retained for the current non-persistent replay session."""

    initial: CubeState
    actions: tuple[str, ...]
    replay: ReplaySession
    stdout: bytes
    stderr: bytes


class CubeVisualizerWindow(QMainWindow):
    """A Qt controller that keeps discrete cube state and animation in sync."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("三维魔方 Solver 可视化")
        self.resize(1360, 860)

        self.runner = SolverRunner(self)
        self.runner.started.connect(self._on_solver_started)
        self.runner.completed.connect(self._on_solver_completed)

        self._session: VisualizerSession | None = None
        self._pending_initial: CubeState | None = None
        # This is the last valid state explicitly previewed or sent to a
        # solver.  "还原到初态" never guesses a solved state from colours.
        self._restore_state: CubeState | None = None
        self._animation_clock = QElapsedTimer()
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(ANIMATION_FRAME_MS)
        self._animation_timer.timeout.connect(self._advance_animation)
        self._animating = False
        self._animation_auto_continue = False

        self._build_ui()
        self._load_sample_state()
        self._update_controls()

    @property
    def session(self) -> VisualizerSession | None:
        """Expose the in-memory run record for lightweight integration tests."""

        return self._session

    def _build_ui(self) -> None:
        root = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(root)

        view_panel = QWidget(root)
        view_layout = QVBoxLayout(view_panel)
        view_layout.setContentsMargins(12, 12, 12, 12)
        self.cube_view = CubeView(view_panel)
        view_layout.addWidget(self.cube_view, stretch=1)

        camera_row = QHBoxLayout()
        self.reset_camera_button = QPushButton("重置视角")
        self.reset_camera_button.clicked.connect(self.cube_view.reset_camera)
        camera_row.addWidget(self.reset_camera_button)
        self.restore_button = QPushButton("还原到初态")
        self.restore_button.clicked.connect(self._restore_initial_state)
        camera_row.addWidget(self.restore_button)
        self.copy_state_button = QPushButton("复制当前状态")
        self.copy_state_button.clicked.connect(self._copy_current_state)
        camera_row.addWidget(self.copy_state_button)
        camera_row.addStretch(1)
        camera_tip = QLabel("左键拖动旋转视角；滚轮缩放")
        camera_tip.setStyleSheet("color: #667085;")
        camera_row.addWidget(camera_tip)
        view_layout.addLayout(camera_row)

        self.current_action_label = QLabel("当前动作：—")
        self.current_action_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        view_layout.addWidget(self.current_action_label)
        self.final_label = QLabel("最终复原：等待 solver 输出")
        view_layout.addWidget(self.final_label)

        control_panel = QWidget(root)
        control_panel.setMinimumWidth(430)
        control_panel.setMaximumWidth(560)
        controls = QVBoxLayout(control_panel)
        controls.setContentsMargins(12, 12, 12, 12)
        controls.setSpacing(10)

        input_group = QGroupBox("初态输入（将原样写入 solver stdin）")
        input_layout = QVBoxLayout(input_group)
        self.input_editor = QPlainTextEdit()
        self.input_editor.setPlaceholderText("按 back, down, front, left, right, up 六个区块输入。")
        self.input_editor.setMinimumHeight(290)
        self.input_editor.setTabChangesFocus(True)
        input_layout.addWidget(self.input_editor)
        input_buttons = QHBoxLayout()
        self.preview_button = QPushButton("预览初态")
        self.preview_button.clicked.connect(self._preview_input)
        self.sample_button = QPushButton("载入题面示例")
        self.sample_button.clicked.connect(self._load_sample_state)
        input_buttons.addWidget(self.preview_button)
        input_buttons.addWidget(self.sample_button)
        input_layout.addLayout(input_buttons)
        controls.addWidget(input_group)

        manual_group = QGroupBox("手动旋转")
        manual_layout = QVBoxLayout(manual_group)
        manual_tip = QLabel("输入空白分隔的课程动作（例如：3- 6+ 4-），将从当前离散状态开始播放。")
        manual_tip.setWordWrap(True)
        manual_tip.setStyleSheet("color: #667085;")
        manual_layout.addWidget(manual_tip)
        manual_row = QHBoxLayout()
        self.manual_actions_input = QLineEdit()
        self.manual_actions_input.setPlaceholderText("例如：0+ 6- 4+")
        self.manual_actions_input.returnPressed.connect(self._run_manual_actions)
        self.manual_rotate_button = QPushButton("旋转")
        self.manual_rotate_button.clicked.connect(self._run_manual_actions)
        manual_row.addWidget(self.manual_actions_input, stretch=1)
        manual_row.addWidget(self.manual_rotate_button)
        manual_layout.addLayout(manual_row)
        controls.addWidget(manual_group)

        solver_group = QGroupBox("学生 solver（已编译 executable）")
        solver_layout = QGridLayout(solver_group)
        self.solver_path = QLineEdit()
        self.solver_path.setPlaceholderText("选择或粘贴可执行文件的绝对路径")
        self.choose_solver_button = QPushButton("选择…")
        self.choose_solver_button.clicked.connect(self._choose_solver)
        self.run_button = QPushButton("运行 solver")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self._run_solver)
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self._stop_solver)
        solver_layout.addWidget(self.solver_path, 0, 0)
        solver_layout.addWidget(self.choose_solver_button, 0, 1)
        solver_layout.addWidget(self.run_button, 1, 0)
        solver_layout.addWidget(self.stop_button, 1, 1)
        controls.addWidget(solver_group)

        replay_group = QGroupBox("动作时间轴")
        replay_layout = QVBoxLayout(replay_group)
        replay_buttons = QHBoxLayout()
        self.previous_button = QPushButton("上一步")
        self.previous_button.clicked.connect(self._previous_step)
        self.play_button = QPushButton("播放")
        self.play_button.clicked.connect(self._toggle_playback)
        self.next_button = QPushButton("下一步")
        self.next_button.clicked.connect(self._next_step)
        replay_buttons.addWidget(self.previous_button)
        replay_buttons.addWidget(self.play_button)
        replay_buttons.addWidget(self.next_button)
        replay_layout.addLayout(replay_buttons)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.valueChanged.connect(self._seek_step)
        replay_layout.addWidget(self.progress_slider)
        self.progress_label = QLabel("第 0 / 0 步")
        replay_layout.addWidget(self.progress_label)
        controls.addWidget(replay_group)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.status_label.setContentsMargins(8, 8, 8, 8)
        controls.addWidget(self.status_label)

        output_tabs = QTabWidget()
        self.actions_output = QPlainTextEdit()
        self.actions_output.setReadOnly(True)
        self.actions_output.setPlaceholderText("solver 成功后会显示已验证的动作序列。")
        self.stdout_output = QPlainTextEdit()
        self.stdout_output.setReadOnly(True)
        self.stdout_output.setPlaceholderText("stdout 只能包含动作 token。")
        self.stderr_output = QPlainTextEdit()
        self.stderr_output.setReadOnly(True)
        self.stderr_output.setPlaceholderText("学生 solver 的 stderr 会单独显示在这里。")
        output_tabs.addTab(self.actions_output, "动作")
        output_tabs.addTab(self.stdout_output, "stdout")
        output_tabs.addTab(self.stderr_output, "stderr / 错误")
        controls.addWidget(output_tabs, stretch=1)

        root.addWidget(view_panel)
        root.addWidget(control_panel)
        root.setStretchFactor(0, 1)
        root.setStretchFactor(1, 0)
        root.setSizes([860, 500])

    def _load_sample_state(self) -> None:
        self.input_editor.setPlainText(SAMPLE_INPUT)
        self._preview_input()

    @Slot()
    def _preview_input(self) -> None:
        """Parse input for the view without changing a completed run record."""

        try:
            state = parse_course_input(self.input_editor.toPlainText())
        except (TypeError, ValueError) as error:
            self._set_status(f"初态格式错误：{error}", error=True)
            return
        if self._animating:
            self._cancel_animation()
        if self._session is not None:
            self._session.replay.pause()
        self._restore_state = state
        self.cube_view.set_state(state)
        self._set_status("初态格式有效，已显示在三维视图中。")
        self._update_controls()

    @Slot()
    def _restore_initial_state(self) -> None:
        """Return to the last valid initial state without assuming it is solved."""

        if self.runner.is_running or self._restore_state is None:
            return
        self._clear_session()
        self.cube_view.set_state(self._restore_state)
        self._set_status("已还原到最近一次预览或运行时的初态。")
        self._update_controls()

    @Slot()
    def _copy_current_state(self) -> None:
        """Copy a canonical course-input representation of the discrete state."""

        text = format_course_input(self.cube_view.state)
        QApplication.clipboard().setText(text)
        self._set_status("已复制当前离散状态；可直接粘贴到初态输入框或 solver stdin。")

    @Slot()
    def _run_manual_actions(self) -> None:
        """Animate a user-entered action sequence from the currently displayed state."""

        if self.runner.is_running:
            return
        raw_actions = self.manual_actions_input.text()
        tokens = tuple(raw_actions.split())
        if not tokens:
            self._set_status("请输入至少一个动作，例如：3- 6+ 4-。", error=True)
            return
        for index, token in enumerate(tokens, start=1):
            try:
                describe_move(token)
            except (TypeError, ValueError) as error:
                self._set_status(f"手动动作第 {index} 项无效：{error}", error=True)
                return

        # Cancelling first restores a partially animated turn to its exact
        # discrete pre-turn state.  That is the only state used as the manual
        # sequence's initial state, so copying and animation cannot diverge.
        self._cancel_animation()
        initial = self.cube_view.state
        self._clear_session()
        replay = ReplaySession(initial, tokens)
        self._session = VisualizerSession(
            initial=initial,
            actions=tokens,
            replay=replay,
            stdout=b"",
            stderr=b"",
        )
        self.actions_output.setPlainText(self._format_actions(tokens))
        self.cube_view.set_state(initial)
        self._set_slider_position(0, maximum=replay.total_steps)
        self._update_timeline_labels()
        self.final_label.setText("最终复原：手动旋转中")
        self.final_label.setStyleSheet("")
        self._set_status(f"正在手动播放 {len(tokens)} 个动作。")
        replay.play()
        self._start_next_animation(auto_continue=True)
        self._update_controls()

    @Slot()
    def _choose_solver(self) -> None:
        file_filter = (
            "Windows 可执行文件 (*.exe);;所有文件 (*)"
            if sys.platform.startswith("win")
            else "所有文件 (*)"
        )
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择学生 solver 可执行文件",
            self.solver_path.text() or str(Path.home()),
            file_filter,
        )
        if selected:
            program = Path(selected).expanduser().resolve()
            self.solver_path.setText(str(program))
            problem = solver_program_problem(program)
            if problem is not None:
                self._set_status(problem, error=True)

    @Slot()
    def _run_solver(self) -> None:
        if self.runner.is_running:
            return
        raw_input = self.input_editor.toPlainText()
        try:
            initial = parse_course_input(raw_input)
        except (TypeError, ValueError) as error:
            self._set_status(f"不能运行：初态格式错误：{error}", error=True)
            return

        raw_path = self.solver_path.text().strip()
        if not raw_path:
            self._set_status("请选择学生已编译的 solver executable。", error=True)
            return
        program = Path(raw_path).expanduser()
        if not program.is_absolute():
            self._set_status("solver 必须使用绝对路径。", error=True)
            return
        program = program.resolve()
        problem = solver_program_problem(program)
        if problem is not None:
            self._set_status(problem, error=True)
            return

        self._pending_initial = initial
        self._restore_state = initial
        self.stdout_output.clear()
        self.stderr_output.clear()
        self._set_status("正在启动 solver；最长等待 5 分钟，stdout/stderr 各最多 1 MiB。")
        try:
            # Do not normalize, canonicalize, or append a newline here: the
            # exact editor text is the protocol bytes supplied to the solver.
            self.runner.run(str(program), raw_input)
        except (TypeError, ValueError, RuntimeError) as error:
            self._pending_initial = None
            self._set_status(f"不能启动 solver：{error}", error=True)
            return
        self._update_controls()

    @Slot()
    def _stop_solver(self) -> None:
        if self.runner.cancel():
            self._set_status("正在停止 solver…")
            self._update_controls()

    @Slot(str)
    def _on_solver_started(self, program: str) -> None:
        # A real child process has begun, so the old volatile session is no
        # longer the current run.  Failed-to-start attempts intentionally do
        # not erase it.
        self._clear_session()
        if self._pending_initial is not None:
            self.cube_view.set_state(self._pending_initial)
        self._set_status(f"solver 已启动：{program}")
        self._update_controls()

    @Slot(object)
    def _on_solver_completed(self, result: SolverResult) -> None:
        self._pending_initial, initial = None, self._pending_initial
        self.stdout_output.setPlainText(result.stdout_text)
        self.stderr_output.setPlainText(result.stderr_text)
        self._update_controls()

        if not result.ok:
            self._set_status(
                f"solver 未产生可播放结果：{result.message}（{result.elapsed_ms} ms）",
                error=True,
            )
            return
        if initial is None:
            self._set_status("内部错误：找不到本次 solver 的初态。", error=True)
            return
        if not result.actions and not is_goal(initial):
            self._set_status(
                "solver stdout 为空；只有初态已经六面同色时，空动作序列才算完成。",
                error=True,
            )
            return

        replay = ReplaySession(initial, result.actions)
        self._session = VisualizerSession(
            initial=initial,
            actions=result.actions,
            replay=replay,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        self.actions_output.setPlainText(self._format_actions(result.actions))
        self.cube_view.set_state(initial)
        self._set_slider_position(0)
        self._update_timeline_labels()
        self._set_status(
            f"已验证 {len(result.actions)} 个动作（solver 用时 {result.elapsed_ms} ms）。"
        )

        # A successful run begins playing immediately.  An already-solved
        # empty sequence remains at step zero and is reported as complete.
        if result.actions:
            replay.play()
            self._start_next_animation(auto_continue=True)
        else:
            self._report_completion()
        self._update_controls()

    def _clear_session(self) -> None:
        self._cancel_animation()
        self._session = None
        self.actions_output.clear()
        self.current_action_label.setText("当前动作：—")
        self.final_label.setText("最终复原：等待 solver 输出")
        self._set_slider_position(0, maximum=0)
        self.progress_label.setText("第 0 / 0 步")

    def _cancel_animation(self) -> None:
        self._animation_timer.stop()
        if self._animating and self._session is not None:
            # A partially drawn turn never becomes a rule state.  Reset the
            # view to the precomputed discrete state before seeking/pausing.
            self.cube_view.set_state(self._session.replay.current_state)
        self._animating = False
        self._animation_auto_continue = False

    @Slot()
    def _toggle_playback(self) -> None:
        session = self._session
        if session is None:
            return
        replay = session.replay
        if self._animating or replay.playing:
            replay.pause()
            self._cancel_animation()
            self._set_status("回放已暂停。")
        else:
            if replay.completed:
                replay.seek(0)
                self.cube_view.set_state(replay.current_state)
                self._set_slider_position(0)
            replay.play()
            self._start_next_animation(auto_continue=True)
        self._update_timeline_labels()
        self._update_controls()

    @Slot()
    def _previous_step(self) -> None:
        session = self._session
        if session is None:
            return
        self._cancel_animation()
        session.replay.previous()
        self.cube_view.set_state(session.replay.current_state)
        self._set_slider_position(session.replay.index)
        self._update_timeline_labels()
        self._update_controls()

    @Slot()
    def _next_step(self) -> None:
        session = self._session
        if session is None or session.replay.completed:
            return
        self._cancel_animation()
        session.replay.pause()
        self._start_next_animation(auto_continue=False)
        self._update_timeline_labels()
        self._update_controls()

    @Slot(int)
    def _seek_step(self, index: int) -> None:
        session = self._session
        if session is None:
            return
        self._cancel_animation()
        try:
            session.replay.seek(index)
        except (IndexError, TypeError):  # Slider values are normally safe.
            return
        self.cube_view.set_state(session.replay.current_state)
        self._set_slider_position(session.replay.index)
        self._update_timeline_labels()
        self._update_controls()
        if session.replay.completed:
            self._report_completion()

    def _start_next_animation(self, *, auto_continue: bool) -> None:
        session = self._session
        if session is None or self._animating:
            return
        replay = session.replay
        token = replay.next_action
        if token is None:
            replay.pause()
            self._report_completion()
            return
        self._animating = True
        self._animation_auto_continue = auto_continue
        self._animation_clock.start()
        self.cube_view.set_animation(replay.current_state, token, 0.0)
        self._animation_timer.start()

    @Slot()
    def _advance_animation(self) -> None:
        session = self._session
        if session is None or not self._animating:
            self._animation_timer.stop()
            return
        replay = session.replay
        token = replay.next_action
        if token is None:
            self._cancel_animation()
            self._report_completion()
            return
        progress = min(1.0, self._animation_clock.elapsed() / ANIMATION_DURATION_MS)
        self.cube_view.set_animation(replay.current_state, token, progress)
        if progress < 1.0:
            return

        self._animation_timer.stop()
        continue_after = self._animation_auto_continue
        self._animating = False
        self._animation_auto_continue = False
        replay.next()  # Commit exactly the already-precomputed next state.
        self.cube_view.set_state(replay.current_state)
        self._set_slider_position(replay.index)
        self._update_timeline_labels()
        self._update_controls()

        if replay.completed:
            self._report_completion()
        elif continue_after and replay.playing:
            QTimer.singleShot(45, self._continue_playback_if_needed)

    @Slot()
    def _continue_playback_if_needed(self) -> None:
        session = self._session
        if session is not None and session.replay.playing and not self._animating:
            self._start_next_animation(auto_continue=True)

    def _set_slider_position(self, index: int, *, maximum: int | None = None) -> None:
        blocker = QSignalBlocker(self.progress_slider)
        if maximum is not None:
            self.progress_slider.setRange(0, maximum)
        self.progress_slider.setValue(index)
        del blocker

    def _update_timeline_labels(self) -> None:
        session = self._session
        if session is None:
            self.current_action_label.setText("当前动作：—")
            self.progress_label.setText("第 0 / 0 步")
            return
        replay = session.replay
        self.progress_slider.setMaximum(replay.total_steps)
        self.progress_label.setText(f"第 {replay.index} / {replay.total_steps} 步")
        if self._animating and replay.next_action is not None:
            action = replay.next_action
            text = f"当前动作：{action}（动画中，第 {replay.index + 1} 步）"
        elif replay.current_action is not None:
            text = f"当前动作：{replay.current_action}（已完成第 {replay.index} 步）"
        else:
            text = "当前动作：—（初态）"
        self.current_action_label.setText(text)

    def _report_completion(self) -> None:
        session = self._session
        if session is None or not session.replay.completed:
            return
        solved = is_goal(session.replay.current_state)
        if solved:
            self.final_label.setText("最终复原：是（六面均为单色）")
            self.final_label.setStyleSheet("color: #147a3d; font-weight: 600;")
            self._set_status("动作序列已播放完毕，魔方已复原。")
        else:
            self.final_label.setText("最终复原：否（动作序列结束但状态未复原）")
            self.final_label.setStyleSheet("color: #b54708; font-weight: 600;")
            self._set_status("动作序列已播放完毕，但最终状态并未复原。", error=True)
        self._update_controls()

    def _format_actions(self, actions: tuple[str, ...]) -> str:
        if not actions:
            return "（空动作序列；初态已复原）"
        return "\n".join(f"{index + 1:>4}: {token}" for index, token in enumerate(actions))

    def _set_status(self, text: str, *, error: bool = False) -> None:
        color = "#b42318" if error else "#344054"
        background = "#fff3f2" if error else "#f8fafc"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; background: {background}; border: 1px solid #d0d5dd; border-radius: 4px;"
        )

    def _update_controls(self) -> None:
        running = self.runner.is_running
        has_session = self._session is not None
        replay = self._session.replay if self._session is not None else None
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.choose_solver_button.setEnabled(not running)
        self.solver_path.setEnabled(not running)
        self.restore_button.setEnabled(not running and self._restore_state is not None)
        self.manual_actions_input.setEnabled(not running)
        self.manual_rotate_button.setEnabled(not running)
        self.copy_state_button.setEnabled(True)
        self.previous_button.setEnabled(has_session and not running and replay is not None and replay.index > 0)
        self.next_button.setEnabled(has_session and not running and replay is not None and not replay.completed)
        self.progress_slider.setEnabled(has_session and not running)
        if not has_session or replay is None:
            self.play_button.setEnabled(False)
            self.play_button.setText("播放")
            return
        self.play_button.setEnabled(not running and (not replay.completed or replay.total_steps > 0))
        self.play_button.setText("暂停" if self._animating or replay.playing else "播放")

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        self._animation_timer.stop()
        self.runner.cancel()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PySide6 三维魔方 solver 可视化器")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="构造窗口并在一次 Qt 事件循环后退出，供本地环境验证使用。",
    )
    arguments = parser.parse_args(argv)
    # Must precede QApplication on macOS so Qt's internal compositor context
    # shares the exact core-profile format used by CubeView.
    configure_opengl_surface_format()
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationDisplayName("三维魔方 Solver 可视化")
    window = CubeVisualizerWindow()
    window.show()
    if arguments.smoke_test:
        QTimer.singleShot(120, application.quit)
    return application.exec()


if __name__ == "__main__":  # pragma: no cover - exercised by manual launch.
    raise SystemExit(main())
