#!/usr/bin/env python3
"""五子棋对战裁判台。

学生只提交一个 C++ 单文件程序。每个 AI 回合，裁判台都会启动一个全新进程，
把当前棋局的一行 JSON 写入 stdin，并从 stdout 读取唯一的一行 JSON 落子结果。
界面本身是可信裁判：它维护棋盘、判定胜负、拒绝非法棋，并记录双方日志。
"""

from __future__ import annotations

import json
import math
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, messagebox, scrolledtext, ttk
import tkinter as tk
from typing import Any


EMPTY = 0
BLACK = 1
WHITE = 2
DEFAULT_BOARD_SIZE = 15
BOARD_SIZE_CHOICES = (9, 11, 13, 15, 17, 19)
WIN_LENGTH = 5
STONE_NAME = {BLACK: "黑", WHITE: "白"}
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))

RULE_FREESTYLE = "freestyle"
RULE_RENJU_CLASSROOM = "renju_classroom"
RULESET_LABELS = {
    RULE_RENJU_CLASSROOM: "连珠禁手（课堂；先手首子天元）",
    RULE_FREESTYLE: "自由五子棋（无禁手）",
}

MODE_HUMAN_AI = "human_ai"
MODE_AI_AI = "ai_ai"
MODE_DEBUG = "debug"
HUMAN = "human"
PROGRAM = "program"

AUTO_STEP_DELAY_MS = 180
MAX_OUTPUT_CHARS = 1_000_000


@dataclass(frozen=True)
class Move:
    row: int
    col: int
    color: int


@dataclass(frozen=True)
class MoveVerdict:
    """裁判对候选落子的唯一判定结果。"""

    legal: bool
    reason: str = ""
    winner: int = EMPTY
    forbidden: str | None = None


@dataclass
class GomokuState:
    """界面唯一持有的可信棋局状态。外部程序只可提交候选落子。"""

    board_size: int = DEFAULT_BOARD_SIZE
    board: list[list[int]] = field(default_factory=list)
    side_to_move: int = BLACK
    last_move: Move | None = None
    history: list[Move] = field(default_factory=list)
    winner: int = EMPTY
    ruleset: str = RULE_RENJU_CLASSROOM

    def __post_init__(self) -> None:
        if self.board_size < WIN_LENGTH or self.board_size % 2 == 0:
            raise ValueError("棋盘大小必须是大于等于 5 的奇数。")
        if not self.board:
            self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
        elif len(self.board) != self.board_size or any(
            len(row) != self.board_size for row in self.board
        ):
            raise ValueError("board 必须是与 board_size 一致的方阵。")

    def reset(self) -> None:
        self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
        self.side_to_move = BLACK
        self.last_move = None
        self.history.clear()
        self.winner = EMPTY

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.board_size and 0 <= col < self.board_size

    @property
    def opening_center(self) -> tuple[int, int]:
        center = self.board_size // 2
        return center, center

    def is_legal(self, row: int, col: int) -> bool:
        return self.analyze_move(row, col).legal

    def legality_reason(self, row: int, col: int) -> str | None:
        verdict = self.analyze_move(row, col)
        return None if verdict.legal else verdict.reason

    def analyze_move(self, row: int, col: int) -> MoveVerdict:
        """不修改局面地判定一手棋；课堂连珠的禁手由此统一执行。"""
        if self.winner != EMPTY or self.is_draw():
            return MoveVerdict(False, "对局已结束。")
        if not self.in_bounds(row, col):
            return MoveVerdict(False, "落子越界。")
        if self.board[row][col] != EMPTY:
            return MoveVerdict(False, "该位置已有棋子。")

        color = self.side_to_move
        if (
            self.ruleset == RULE_RENJU_CLASSROOM
            and color == BLACK
            and not self.history
            and (row, col) != self.opening_center
        ):
            center_row, center_col = self.opening_center
            coordinate = f"{chr(ord('A') + center_col)}{center_row + 1}"
            return MoveVerdict(
                False,
                "课堂连珠开局要求先手（本局黑方）首手落在天元 "
                f"{coordinate}（[{center_row},{center_col}]）。",
                forbidden="opening",
            )

        self.board[row][col] = color
        try:
            if self.ruleset == RULE_FREESTYLE:
                winner = color if self._has_at_least_five(row, col, color) else EMPTY
                return MoveVerdict(True, winner=winner)

            if color == WHITE:
                winner = WHITE if self._has_at_least_five(row, col, WHITE) else EMPTY
                return MoveVerdict(True, winner=winner)

            # 中国五子棋竞赛规则中的优先级：黑方本手恰好五连时，五连优先于禁手。
            if self._has_exact_five(row, col, BLACK):
                return MoveVerdict(True, winner=BLACK)
            if self._has_overline(row, col, BLACK):
                return MoveVerdict(
                    False,
                    "先手（本局黑方）长连（六子及以上）为禁手，后手获胜。",
                    forbidden="overline",
                )
            if len(self._four_patterns_through(row, col)) >= 2:
                return MoveVerdict(
                    False,
                    "先手（本局黑方）四四（同时形成两个及以上的四）为禁手，后手获胜。",
                    forbidden="double_four",
                )
            if len(self._open_three_patterns_through(row, col)) >= 2:
                return MoveVerdict(
                    False,
                    "先手（本局黑方）三三（同时形成两个及以上的活三）为禁手，后手获胜。",
                    forbidden="double_three",
                )
            return MoveVerdict(True)
        finally:
            self.board[row][col] = EMPTY

    def play(self, row: int, col: int) -> Move:
        verdict = self.analyze_move(row, col)
        if not verdict.legal:
            raise ValueError(verdict.reason)
        move = Move(row, col, self.side_to_move)
        self.board[row][col] = move.color
        self.history.append(move)
        self.last_move = move
        self.winner = verdict.winner
        self.side_to_move = WHITE if move.color == BLACK else BLACK
        return move

    def undo(self) -> Move | None:
        if not self.history:
            return None
        move = self.history.pop()
        self.board[move.row][move.col] = EMPTY
        self.side_to_move = move.color
        self.last_move = self.history[-1] if self.history else None
        self.winner = EMPTY
        return move

    def is_draw(self) -> bool:
        return self.winner == EMPTY and len(self.history) == self.board_size * self.board_size

    def request(self, game_id: str, time_limit_ms: int) -> dict[str, Any]:
        """构造兼容旧字段、且能关联对局与回合的新协议请求。"""
        ply = len(self.history)
        return {
            "protocol_version": "gomoku-1.0",
            "case_id": f"{game_id}:{ply:03d}",
            "game_id": game_id,
            "ply": ply,
            "board_size": self.board_size,
            "board": [row.copy() for row in self.board],
            "side_to_move": self.side_to_move,
            "player_color": self.side_to_move,
            "last_move": (
                [self.last_move.row, self.last_move.col] if self.last_move is not None else None
            ),
            "last_move_color": self.last_move.color if self.last_move is not None else None,
            "rules": {
                "id": self.ruleset,
                "win_length": WIN_LENGTH,
                "black_win": "five_or_more" if self.ruleset == RULE_FREESTYLE else "exactly_five",
                "white_win": "five_or_more",
                "first_player_color": BLACK,
                "first_player_win": (
                    "five_or_more" if self.ruleset == RULE_FREESTYLE else "exactly_five"
                ),
                "forbidden_moves": (
                    "none"
                    if self.ruleset == RULE_FREESTYLE
                    else "first_player_overline_double_four_double_three"
                ),
                "forbidden_player": (
                    "none" if self.ruleset == RULE_FREESTYLE else "first_player_black"
                ),
                "opening": (
                    "free"
                    if self.ruleset == RULE_FREESTYLE
                    else "first_player_center"
                ),
                "opening_center": list(self.opening_center),
                "adjudication": "automatic",
                "time_limit_ms": time_limit_ms,
            },
        }

    def set_ruleset(self, ruleset: str) -> None:
        if ruleset not in RULESET_LABELS:
            raise ValueError(f"未知规则预设：{ruleset}")
        self.ruleset = ruleset

    def _line_length(self, row: int, col: int, color: int, dr: int, dc: int) -> int:
        count = 1
        for sign in (-1, 1):
            r, c = row + sign * dr, col + sign * dc
            while self.in_bounds(r, c) and self.board[r][c] == color:
                count += 1
                r += sign * dr
                c += sign * dc
        return count

    def _has_at_least_five(self, row: int, col: int, color: int) -> bool:
        return any(
            self._line_length(row, col, color, dr, dc) >= WIN_LENGTH
            for dr, dc in DIRECTIONS
        )

    def _has_exact_five(self, row: int, col: int, color: int) -> bool:
        return any(
            self._line_length(row, col, color, dr, dc) == WIN_LENGTH
            for dr, dc in DIRECTIONS
        )

    def _has_overline(self, row: int, col: int, color: int) -> bool:
        return any(
            self._line_length(row, col, color, dr, dc) > WIN_LENGTH
            for dr, dc in DIRECTIONS
        )

    def _four_patterns_through(self, row: int, col: int) -> set[tuple[int, frozenset[tuple[int, int]]]]:
        """枚举含新落子的“四”；活四的两个补点只算同一个四。"""
        patterns: set[tuple[int, frozenset[tuple[int, int]]]] = set()
        for direction, (dr, dc) in enumerate(DIRECTIONS):
            for start in range(-4, 1):
                cells = [(row + (start + index) * dr, col + (start + index) * dc) for index in range(5)]
                if not all(self.in_bounds(r, c) for r, c in cells):
                    continue
                values = [self.board[r][c] for r, c in cells]
                if values.count(BLACK) != 4 or values.count(EMPTY) != 1:
                    continue
                empty_row, empty_col = cells[values.index(EMPTY)]
                self.board[empty_row][empty_col] = BLACK
                try:
                    completes_exact_five = (
                        self._line_length(empty_row, empty_col, BLACK, dr, dc) == WIN_LENGTH
                    )
                finally:
                    self.board[empty_row][empty_col] = EMPTY
                if completes_exact_five:
                    black_cells = frozenset(
                        (cell_row, cell_col)
                        for (cell_row, cell_col), value in zip(cells, values)
                        if value == BLACK
                    )
                    patterns.add((direction, black_cells))
        return patterns

    def _open_three_patterns_through(
        self, row: int, col: int
    ) -> set[tuple[int, frozenset[tuple[int, int]]]]:
        """枚举含新落子的活三：补一子后可形成两端均空的连续活四。"""
        patterns: set[tuple[int, frozenset[tuple[int, int]]]] = set()
        for direction, (dr, dc) in enumerate(DIRECTIONS):
            for extension in range(-3, 4):
                if extension == 0:
                    continue
                extend_row, extend_col = row + extension * dr, col + extension * dc
                if not self.in_bounds(extend_row, extend_col):
                    continue
                if self.board[extend_row][extend_col] != EMPTY:
                    continue
                self.board[extend_row][extend_col] = BLACK
                try:
                    for start in range(-3, 1):
                        cells = [
                            (row + (start + index) * dr, col + (start + index) * dc)
                            for index in range(4)
                        ]
                        if (row, col) not in cells or (extend_row, extend_col) not in cells:
                            continue
                        if not all(self.in_bounds(cell_row, cell_col) for cell_row, cell_col in cells):
                            continue
                        if not all(self.board[cell_row][cell_col] == BLACK for cell_row, cell_col in cells):
                            continue
                        before = (cells[0][0] - dr, cells[0][1] - dc)
                        after = (cells[-1][0] + dr, cells[-1][1] + dc)
                        if not (
                            self.in_bounds(*before)
                            and self.in_bounds(*after)
                            and self.board[before[0]][before[1]] == EMPTY
                            and self.board[after[0]][after[1]] == EMPTY
                        ):
                            continue
                        three_cells = frozenset(cell for cell in cells if cell != (extend_row, extend_col))
                        patterns.add((direction, three_cells))
                finally:
                    self.board[extend_row][extend_col] = EMPTY
        return patterns


class StudentProgram:
    """一份学生 C++ 单文件程序及其独立的临时构建目录。"""

    def __init__(self) -> None:
        self.source_path: Path | None = None
        self.executable_path: Path | None = None
        self.build_dir = Path(tempfile.mkdtemp(prefix="gomoku-player-"))

    @staticmethod
    def find_compiler() -> str | None:
        configured = os.environ.get("CXX")
        if configured and shutil.which(configured):
            return configured
        return shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")

    @property
    def label(self) -> str:
        return self.source_path.name if self.source_path is not None else "未选择程序"

    @property
    def is_ready(self) -> bool:
        return self.executable_path is not None and self.executable_path.exists()

    def select_source(self, source_path: Path) -> None:
        self.source_path = source_path
        self.executable_path = None

    def compile(self) -> tuple[bool, str]:
        if self.source_path is None:
            return False, "请先选择学生的 .cpp 文件。"
        self.executable_path = None
        compiler = self.find_compiler()
        if compiler is None:
            return False, "未找到 C++ 编译器。请安装或把 CXX 指向 c++ / g++ / clang++。"

        suffix = ".exe" if os.name == "nt" else ""
        executable = self.build_dir / f"student_solver{suffix}"
        command = [compiler, "-std=c++17", "-O2", str(self.source_path), "-o", str(executable)]
        try:
            result = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "编译超过 20 秒，已停止。"
        except OSError as error:
            return False, f"无法启动编译器：{error}"

        compiler_text = self._limit_text(result.stdout + result.stderr)
        if result.returncode != 0 or not executable.exists():
            detail = compiler_text or f"编译失败（退出码 {result.returncode}）"
            return False, detail

        self.executable_path = executable
        return True, compiler_text or "编译成功。"

    def run_one_move(
        self,
        request: dict[str, Any],
        timeout_ms: int,
        *,
        require_case_id: bool,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if not self.is_ready or self.executable_path is None:
            return False, "该方程序尚未编译。", None

        stdin_text = json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                [str(self.executable_path)],
                cwd=str(self.build_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name == "posix",
            )
            stdout, stderr = process.communicate(stdin_text, timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            if process is not None:
                self._terminate_process(process)
                stdout, stderr = process.communicate()
            else:
                stdout, stderr = "", ""
            return False, f"程序超过 {timeout_ms} ms，已停止。\nstderr:\n{self._limit_text(stderr).strip()}", None
        except OSError as error:
            return False, f"无法启动学生程序：{error}", None

        stdout = self._limit_text(stdout)
        stderr = self._limit_text(stderr)
        stderr_text = stderr.strip()
        if process.returncode != 0:
            return False, f"学生程序异常退出（退出码 {process.returncode}）。\nstderr:\n{stderr_text}", None
        if len(stdout) >= MAX_OUTPUT_CHARS or len(stderr) >= MAX_OUTPUT_CHARS:
            return False, "程序输出超过 1 MiB 限制。", None

        nonempty_lines = [line for line in stdout.splitlines() if line.strip()]
        if len(nonempty_lines) != 1:
            return False, (
                "stdout 必须只包含一行 JSON Response。\n"
                f"实际 stdout:\n{stdout.strip()}\n"
                f"stderr:\n{stderr_text}"
            ), None

        try:
            response = json.loads(nonempty_lines[0])
        except json.JSONDecodeError as error:
            return False, f"stdout 不是合法 JSON：{error}\n原文：{nonempty_lines[0]}", None
        if not isinstance(response, dict):
            return False, "Response 必须是 JSON 对象。", None

        expected_case_id = request["case_id"]
        if require_case_id and response.get("case_id") != expected_case_id:
            return False, f"Response 必须携带匹配的 case_id：{expected_case_id}。", None
        if not require_case_id and response.get("case_id") not in (None, expected_case_id):
            return False, "Response 的 case_id 与 Request 不匹配。", None

        move = response.get("move")
        if not (
            isinstance(move, list)
            and len(move) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in move)
        ):
            return False, "move 必须是两个 0-based 整数 [row,col]。", None

        log = f"stdout: {nonempty_lines[0]}"
        if stderr_text:
            log += f"\nstderr:\n{stderr_text}"
        return True, log, response

    @staticmethod
    def _limit_text(text: str) -> str:
        if len(text) < MAX_OUTPUT_CHARS:
            return text
        return text[:MAX_OUTPUT_CHARS] + "\n[输出已截断]"

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError):
                pass
        process.kill()

    def close(self) -> None:
        shutil.rmtree(self.build_dir, ignore_errors=True)


@dataclass
class PlayerSlot:
    """一个稳定的参赛者；color 只表示其当前这盘所执的棋色。"""

    player_id: str
    program: StudentProgram = field(default_factory=StudentProgram)
    kind: str = HUMAN


@dataclass
class SeriesScore:
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: float = 0.0


class GomokuApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("五子棋对战裁判台")
        self.root.minsize(1120, 740)
        self.root.geometry("1360x860")

        self.ruleset_var = StringVar(value=RULE_RENJU_CLASSROOM)
        self.board_size_var = StringVar(value=str(DEFAULT_BOARD_SIZE))
        self.state = GomokuState(
            board_size=int(self.board_size_var.get()), ruleset=self.ruleset_var.get()
        )
        self.players = {BLACK: PlayerSlot("A"), WHITE: PlayerSlot("B")}
        self.jobs: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.busy = False
        self.match_active = False
        self.paused = False
        self.game_id = self._new_game_id()
        self.revision = 0
        self.forfeit_color: int | None = None
        self.result_detail = ""
        self.series_active = False
        self.series_id = ""
        self.series_round = 0
        self.series_total_rounds = 1
        self.series_game_recorded = False
        self.series_points = (1.0, 0.5, 0.0)
        self.series_scores: dict[str, SeriesScore] = {}
        self.series_names: dict[str, str] = {}
        self.series_first_players: list[str] = []

        self.board_cell = 40.0
        self.board_origin = (42.0, 42.0)

        self.mode_var = StringVar(value=MODE_HUMAN_AI)
        self.human_color_var = StringVar(value="black")
        self.time_limit_var = StringVar(value="2000")
        self.rounds_var = StringVar(value="2")
        self.win_points_var = StringVar(value="1")
        self.draw_points_var = StringVar(value="0.5")
        self.loss_points_var = StringVar(value="0")
        self.status_var = StringVar(value="请选择模式和选手，随后点击“开始 / 重新开始”。")
        self.turn_var = StringVar()
        self.position_var = StringVar()
        self.coordinate_help_var = StringVar()
        self.series_summary_var = StringVar(value="仅在 C++ 程序 vs C++ 程序模式下启用系列赛。")
        self.player_role_vars = {BLACK: StringVar(), WHITE: StringVar()}
        self.player_source_vars = {BLACK: StringVar(), WHITE: StringVar()}
        self.player_build_vars = {BLACK: StringVar(), WHITE: StringVar()}
        self.player_choose_buttons: dict[int, ttk.Button] = {}
        self.player_compile_buttons: dict[int, ttk.Button] = {}
        self.mode_widgets: list[ttk.Widget] = []
        self.human_color_widgets: list[ttk.Widget] = []
        self.rule_widgets: list[ttk.Widget] = []
        self.match_setting_widgets: list[ttk.Widget] = []
        self.series_setting_widgets: list[ttk.Widget] = []
        self.board_size_selector: ttk.Combobox | None = None

        self._build_ui()
        self._apply_mode()
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll_jobs)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Helvetica", 16, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 11, "bold"))
        style.configure("Player.TLabel", font=("Helvetica", 11, "bold"))

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)
        outer.rowconfigure(1, weight=1)

        ttk.Label(outer, text="五子棋 · 对战裁判台", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel", wraplength=520).grid(
            row=0, column=1, sticky="e", padx=(16, 0)
        )

        board_area = ttk.Frame(outer)
        board_area.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        board_area.columnconfigure(0, weight=1)
        board_area.rowconfigure(0, weight=1)
        self.board_canvas = tk.Canvas(
            board_area,
            background="#e6bd75",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.board_canvas.grid(row=0, column=0, sticky="nsew")
        self.board_canvas.bind("<Configure>", lambda _event: self._draw_board())
        self.board_canvas.bind("<Button-1>", self._on_board_click)

        controls = ttk.Frame(board_area, padding=(0, 10, 0, 0))
        controls.grid(row=1, column=0, sticky="ew")
        self.start_button = ttk.Button(controls, text="开始 / 重新开始", command=self._start_match)
        self.start_button.pack(side="left")
        self.stop_series_button = ttk.Button(controls, text="终止系列赛", command=self._stop_series)
        self.stop_series_button.pack(side="left", padx=(6, 0))
        self.pause_button = ttk.Button(controls, text="暂停", command=self._pause_or_resume)
        self.pause_button.pack(side="left", padx=(6, 0))
        self.step_button = ttk.Button(controls, text="单步 AI", command=self._single_step)
        self.step_button.pack(side="left")
        self.undo_button = ttk.Button(controls, text="悔一步", command=self._undo)
        self.undo_button.pack(side="left", padx=6)
        self.swap_button = ttk.Button(controls, text="交换黑白程序", command=self._swap_players)
        self.swap_button.pack(side="left")
        ttk.Button(controls, text="复制当前 Request", command=self._copy_request).pack(side="right")

        side = ttk.Frame(outer, width=430)
        side.grid(row=1, column=1, sticky="ns", padx=(14, 0), pady=(12, 0))
        side.grid_propagate(False)

        mode_box = ttk.LabelFrame(side, text="对战模式", padding=10)
        mode_box.pack(fill="x")
        for value, text in (
            (MODE_HUMAN_AI, "玩家 vs C++ 程序"),
            (MODE_AI_AI, "C++ 程序 vs C++ 程序（系列赛）"),
            (MODE_DEBUG, "自由摆棋（调试）"),
        ):
            widget = ttk.Radiobutton(
                mode_box,
                text=text,
                value=value,
                variable=self.mode_var,
                command=self._on_mode_changed,
            )
            widget.pack(anchor="w")
            self.mode_widgets.append(widget)

        human_side = ttk.Frame(mode_box)
        human_side.pack(fill="x", pady=(6, 0))
        ttk.Label(human_side, text="玩家执：").pack(side="left")
        for value, text in (("black", "黑"), ("white", "白")):
            widget = ttk.Radiobutton(
                human_side,
                text=text,
                value=value,
                variable=self.human_color_var,
                command=self._on_human_color_changed,
            )
            widget.pack(side="left", padx=(4, 0))
            self.human_color_widgets.append(widget)

        limits = ttk.Frame(mode_box)
        limits.pack(fill="x", pady=(6, 0))
        ttk.Label(limits, text="每手限时 (ms)：").pack(side="left")
        time_entry = ttk.Entry(limits, textvariable=self.time_limit_var, width=8)
        time_entry.pack(side="left")
        self.match_setting_widgets.append(time_entry)
        ttk.Label(limits, text="棋盘：").pack(side="left", padx=(14, 0))
        board_size_selector = ttk.Combobox(
            limits,
            textvariable=self.board_size_var,
            values=[str(size) for size in BOARD_SIZE_CHOICES],
            state="readonly",
            width=4,
        )
        board_size_selector.pack(side="left")
        board_size_selector.bind("<<ComboboxSelected>>", self._on_board_size_changed)
        self.board_size_selector = board_size_selector

        series_box = ttk.LabelFrame(side, text="C++ vs C++ 系列赛", padding=10)
        series_box.pack(fill="x", pady=(10, 0))
        rounds_line = ttk.Frame(series_box)
        rounds_line.pack(fill="x")
        ttk.Label(rounds_line, text="对战轮次：").pack(side="left")
        rounds_entry = ttk.Entry(rounds_line, textvariable=self.rounds_var, width=7)
        rounds_entry.pack(side="left")
        ttk.Label(rounds_line, text="每局结束后自动交换先手", foreground="#555555").pack(
            side="left", padx=(8, 0)
        )
        points_line = ttk.Frame(series_box)
        points_line.pack(fill="x", pady=(6, 0))
        ttk.Label(points_line, text="积分（胜 / 和 / 负）：").pack(side="left")
        win_entry = ttk.Entry(points_line, textvariable=self.win_points_var, width=5)
        win_entry.pack(side="left")
        ttk.Label(points_line, text="/").pack(side="left", padx=3)
        draw_entry = ttk.Entry(points_line, textvariable=self.draw_points_var, width=5)
        draw_entry.pack(side="left")
        ttk.Label(points_line, text="/").pack(side="left", padx=3)
        loss_entry = ttk.Entry(points_line, textvariable=self.loss_points_var, width=5)
        loss_entry.pack(side="left")
        ttk.Label(series_box, textvariable=self.series_summary_var, wraplength=390).pack(
            anchor="w", pady=(7, 0)
        )
        self.series_setting_widgets.extend((rounds_entry, win_entry, draw_entry, loss_entry))

        ttk.Label(mode_box, text="裁判规则：").pack(anchor="w", pady=(8, 0))
        for value in (RULE_RENJU_CLASSROOM, RULE_FREESTYLE):
            widget = ttk.Radiobutton(
                mode_box,
                text=RULESET_LABELS[value],
                value=value,
                variable=self.ruleset_var,
                command=self._on_ruleset_changed,
            )
            widget.pack(anchor="w")
            self.rule_widgets.append(widget)

        self._build_player_card(side, BLACK)
        self._build_player_card(side, WHITE)

        state_box = ttk.LabelFrame(side, text="棋局", padding=10)
        state_box.pack(fill="x", pady=(10, 0))
        ttk.Label(state_box, textvariable=self.turn_var).pack(anchor="w")
        ttk.Label(state_box, textvariable=self.position_var).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            state_box,
            textvariable=self.coordinate_help_var,
            foreground="#555555",
            wraplength=390,
        ).pack(anchor="w", pady=(7, 0))

        request_box = ttk.LabelFrame(side, text="当前 Request（调试）", padding=6)
        request_box.pack(fill="both", expand=True, pady=(10, 0))
        self.request_text = scrolledtext.ScrolledText(
            request_box, height=10, wrap="word", font=("Menlo", 10), state="disabled"
        )
        self.request_text.pack(fill="both", expand=True)

        log_box = ttk.LabelFrame(side, text="对局 / 编译日志", padding=6)
        log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(
            log_box, height=10, wrap="word", font=("Menlo", 10), state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

    def _build_player_card(self, parent: ttk.Frame, color: int) -> None:
        card = ttk.LabelFrame(parent, text=f"{STONE_NAME[color]}方选手", padding=10)
        card.pack(fill="x", pady=(10, 0))
        ttk.Label(card, textvariable=self.player_role_vars[color], style="Player.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=self.player_source_vars[color], wraplength=390).pack(
            anchor="w", pady=(3, 0)
        )
        buttons = ttk.Frame(card)
        buttons.pack(fill="x", pady=(7, 0))
        choose = ttk.Button(buttons, text="选择 .cpp", command=lambda c=color: self._choose_source(c))
        choose.pack(side="left")
        compile_button = ttk.Button(buttons, text="编译", command=lambda c=color: self._compile_player(c))
        compile_button.pack(side="left", padx=6)
        ttk.Label(buttons, textvariable=self.player_build_vars[color], foreground="#555555").pack(
            side="left", padx=(6, 0)
        )
        self.player_choose_buttons[color] = choose
        self.player_compile_buttons[color] = compile_button

    def _time_limit(self, *, show_error: bool = True) -> int | None:
        try:
            value = int(self.time_limit_var.get())
        except ValueError:
            if show_error:
                self._set_status("单步限时必须是正整数。", error=True)
            return None
        if not 50 <= value <= 60_000:
            if show_error:
                self._set_status("单步限时请设在 50–60000 ms。", error=True)
            return None
        return value

    def _current_request(self, *, show_error: bool = False) -> dict[str, Any] | None:
        limit = self._time_limit(show_error=show_error)
        if limit is None:
            return None
        return self.state.request(self.game_id, limit)

    def _apply_mode(self) -> None:
        mode = self.mode_var.get()
        if mode == MODE_AI_AI:
            self.players[BLACK].kind = PROGRAM
            self.players[WHITE].kind = PROGRAM
        elif mode == MODE_HUMAN_AI:
            human_color = BLACK if self.human_color_var.get() == "black" else WHITE
            self.players[BLACK].kind = HUMAN if BLACK == human_color else PROGRAM
            self.players[WHITE].kind = HUMAN if WHITE == human_color else PROGRAM
        else:
            self.players[BLACK].kind = HUMAN
            self.players[WHITE].kind = HUMAN

    def _on_mode_changed(self) -> None:
        if self.busy or self.match_active or self.series_active:
            return
        self.paused = False
        self._apply_mode()
        self._set_status("模式已切换；点击“开始 / 重新开始”会建立新对局。")
        self._refresh()

    def _on_human_color_changed(self) -> None:
        if self.mode_var.get() != MODE_HUMAN_AI or self.busy or self.match_active or self.series_active:
            return
        self.paused = False
        self._apply_mode()
        self._set_status("玩家执子已切换；点击“开始 / 重新开始”会建立新对局。")
        self._refresh()

    def _on_ruleset_changed(self) -> None:
        if self.busy or self.match_active or self.series_active:
            return
        self.state.set_ruleset(self.ruleset_var.get())
        self._set_status(f"裁判规则已切换为：{RULESET_LABELS[self.state.ruleset]}。")
        self._refresh()

    def _on_board_size_changed(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self.busy or self.match_active or self.series_active:
            return
        try:
            board_size = int(self.board_size_var.get())
        except ValueError:
            self.board_size_var.set(str(self.state.board_size))
            self._set_status("棋盘大小必须是预设的奇数尺寸。", error=True)
            return
        if board_size not in BOARD_SIZE_CHOICES:
            self.board_size_var.set(str(self.state.board_size))
            self._set_status("请选择界面提供的棋盘大小。", error=True)
            return
        self.state = GomokuState(board_size=board_size, ruleset=self.ruleset_var.get())
        self.game_id = self._new_game_id()
        self.revision += 1
        self._set_status(f"棋盘已切换为 {board_size}×{board_size}；点击“开始 / 重新开始”建立新局。")
        self._refresh()

    def _required_program_colors(self) -> list[int]:
        return [color for color in (BLACK, WHITE) if self.players[color].kind == PROGRAM]

    def _finished(self) -> bool:
        return bool(self.result_detail) or self.state.winner != EMPTY or self.state.is_draw()

    def _result_text(self) -> str:
        if self.forfeit_color is not None:
            winner = WHITE if self.forfeit_color == BLACK else BLACK
            return (
                f"对局结束：{STONE_NAME[winner]}方获胜"
                f"（{STONE_NAME[self.forfeit_color]}方判负：{self.result_detail}）"
            )
        if self.state.winner:
            return f"对局结束：{STONE_NAME[self.state.winner]}方五连获胜"
        if self.state.is_draw():
            return "对局结束：和棋"
        return ""

    def _series_summary(self) -> str:
        if self.mode_var.get() != MODE_AI_AI:
            return "仅在 C++ 程序 vs C++ 程序模式下启用系列赛。"
        if not self.series_scores:
            return "尚未开始系列赛。每局结束后，两份程序自动交换先手。"
        entries: list[str] = []
        for player_id in sorted(self.series_scores):
            score = self.series_scores[player_id]
            name = self.series_names.get(player_id, f"选手 {player_id}")
            entries.append(
                f"{player_id}（{name}）：{score.wins}胜 {score.draws}和 {score.losses}负，"
                f"{score.points:g} 分"
            )
        progress = f"第 {self.series_round}/{self.series_total_rounds} 局"
        return f"{progress}；" + "；".join(entries)

    def _refresh(self) -> None:
        if self._finished():
            self.turn_var.set(self._result_text())
        elif not self.match_active:
            self.turn_var.set("尚未开始；配置后点击“开始 / 重新开始”。")
        elif self.paused:
            self.turn_var.set(f"已暂停：轮到 {STONE_NAME[self.state.side_to_move]}方")
        else:
            kind = self.players[self.state.side_to_move].kind
            detail = "等待玩家点击棋盘" if kind == HUMAN else "正在由 C++ 程序计算"
            self.turn_var.set(f"轮到 {STONE_NAME[self.state.side_to_move]}方：{detail}")

        last = "无"
        if self.state.last_move:
            last = (
                f"{STONE_NAME[self.state.last_move.color]} "
                f"{self._coordinate(self.state.last_move.row, self.state.last_move.col)}"
            )
        self.position_var.set(
            f"{self.state.board_size}×{self.state.board_size}；{RULESET_LABELS[self.state.ruleset]}；"
            f"对局 {self.game_id}；"
            f"已落 {len(self.state.history)} 手；上一手：{last}"
        )
        last_column = chr(ord("A") + self.state.board_size - 1)
        self.coordinate_help_var.set(
            f"坐标为 0-based [row,col]；棋盘标注为 A–{last_column} 与 1–{self.state.board_size}。"
        )
        self.series_summary_var.set(self._series_summary())

        request = self._current_request()
        if request is not None:
            self._set_text(self.request_text, json.dumps(request, ensure_ascii=False, indent=2))
        self._refresh_player_cards()
        self._refresh_controls()
        self._draw_board()

    def _refresh_player_cards(self) -> None:
        for color in (BLACK, WHITE):
            slot = self.players[color]
            if slot.kind == HUMAN:
                self.player_role_vars[color].set(
                    f"选手 {slot.player_id} · 人类玩家（点击棋盘落子）"
                )
            else:
                self.player_role_vars[color].set(
                    f"选手 {slot.player_id} · C++ 程序（每手启动一个新进程）"
                )

            if slot.program.source_path is None:
                self.player_source_vars[color].set("未选择 .cpp 文件")
                self.player_build_vars[color].set("待选择")
            else:
                self.player_source_vars[color].set(str(slot.program.source_path))
                self.player_build_vars[color].set("已编译" if slot.program.is_ready else "待编译")

    def _refresh_controls(self) -> None:
        match_configuration_enabled = (
            not self.busy and not self.match_active and not self.series_active
        )
        for widget in self.mode_widgets:
            widget.configure(state="normal" if match_configuration_enabled else "disabled")
        for widget in self.rule_widgets:
            widget.configure(state="normal" if match_configuration_enabled else "disabled")
        for widget in self.match_setting_widgets:
            widget.configure(state="normal" if match_configuration_enabled else "disabled")
        if self.board_size_selector is not None:
            self.board_size_selector.configure(
                state="readonly" if match_configuration_enabled else "disabled"
            )
        human_side_enabled = match_configuration_enabled and self.mode_var.get() == MODE_HUMAN_AI
        for widget in self.human_color_widgets:
            widget.configure(state="normal" if human_side_enabled else "disabled")
        series_settings_enabled = match_configuration_enabled and self.mode_var.get() == MODE_AI_AI
        for widget in self.series_setting_widgets:
            widget.configure(state="normal" if series_settings_enabled else "disabled")

        for color in (BLACK, WHITE):
            program_enabled = match_configuration_enabled and self.players[color].kind == PROGRAM
            self.player_choose_buttons[color].configure(state="normal" if program_enabled else "disabled")
            can_compile = (
                not self.busy
                and not self.series_active
                and (not self.match_active or self.paused)
                and self.players[color].kind == PROGRAM
                and self.players[color].program.source_path is not None
            )
            self.player_compile_buttons[color].configure(state="normal" if can_compile else "disabled")

        self.start_button.configure(
            state="normal" if not self.busy and not self.series_active else "disabled"
        )
        self.stop_series_button.configure(
            state="normal" if self.series_active and not self.busy else "disabled"
        )
        pause_enabled = self.match_active and not self._finished()
        self.pause_button.configure(state="normal" if pause_enabled else "disabled")
        self.pause_button.configure(text="继续" if self.paused else "暂停")
        step_enabled = self.match_active and not self.busy and not self._finished()
        self.step_button.configure(state="normal" if step_enabled else "disabled")
        undo_enabled = (
            not self.busy
            and not self.series_active
            and bool(self.state.history)
            and (not self.match_active or self.paused or self._finished())
        )
        self.undo_button.configure(state="normal" if undo_enabled else "disabled")
        self.swap_button.configure(state="normal" if match_configuration_enabled else "disabled")

    def _draw_board(self) -> None:
        canvas = self.board_canvas
        board_size = self.state.board_size
        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 200)
        margin = max(28.0, min(width, height) * 0.065)
        cell = (min(width, height) - 2 * margin) / (board_size - 1)
        board_pixels = cell * (board_size - 1)
        x0 = (width - board_pixels) / 2
        y0 = (height - board_pixels) / 2
        self.board_cell = cell
        self.board_origin = (x0, y0)

        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#e6bd75", outline="")
        for index in range(board_size):
            x = x0 + index * cell
            y = y0 + index * cell
            canvas.create_line(x0, y, x0 + board_pixels, y, fill="#4c3720", width=1)
            canvas.create_line(x, y0, x, y0 + board_pixels, fill="#4c3720", width=1)
            canvas.create_text(x, y0 - 18, text=chr(ord("A") + index), fill="#4c3720", font=("Helvetica", 10))
            canvas.create_text(x0 - 18, y, text=str(index + 1), fill="#4c3720", font=("Helvetica", 10))

        star_radius = max(2, cell * 0.07)
        center = board_size // 2
        offset = max(2, board_size // 4)
        star_points = {
            (center, center),
            (center - offset, center - offset),
            (center - offset, center + offset),
            (center + offset, center - offset),
            (center + offset, center + offset),
        }
        for row, col in star_points:
            x, y = x0 + col * cell, y0 + row * cell
            canvas.create_oval(x - star_radius, y - star_radius, x + star_radius, y + star_radius, fill="#49331d", outline="")

        radius = cell * 0.43
        for row in range(board_size):
            for col in range(board_size):
                color = self.state.board[row][col]
                if color == EMPTY:
                    continue
                x, y = x0 + col * cell, y0 + row * cell
                if color == BLACK:
                    canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#1f1f1f", outline="#080808")
                else:
                    canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#f8f6ed", outline="#555555")

        if self.state.last_move:
            x = x0 + self.state.last_move.col * cell
            y = y0 + self.state.last_move.row * cell
            marker = max(2.5, cell * 0.09)
            canvas.create_oval(x - marker, y - marker, x + marker, y + marker, fill="#e34b2d", outline="")

    def _on_board_click(self, event: tk.Event[tk.Misc]) -> None:
        if self.busy:
            self._set_status("正在等待 C++ 程序返回，本回合棋盘已锁定。", error=True)
            return
        if not self.match_active:
            self._set_status("请先点击“开始 / 重新开始”。", error=True)
            return
        if self.paused:
            self._set_status("对局已暂停；请继续对局后再落子。", error=True)
            return
        if self._finished():
            self._set_status(self._result_text(), error=True)
            return
        if self.players[self.state.side_to_move].kind != HUMAN:
            self._set_status(f"现在轮到 {STONE_NAME[self.state.side_to_move]}方程序落子。", error=True)
            return

        x0, y0 = self.board_origin
        col = round((event.x - x0) / self.board_cell)
        row = round((event.y - y0) / self.board_cell)
        x = x0 + col * self.board_cell
        y = y0 + row * self.board_cell
        if (
            not self.state.in_bounds(row, col)
            or abs(event.x - x) > self.board_cell * 0.45
            or abs(event.y - y) > self.board_cell * 0.45
        ):
            return
        verdict = self.state.analyze_move(row, col)
        if not verdict.legal:
            if verdict.forbidden is not None:
                self._declare_forfeit(self.state.side_to_move, verdict.reason)
                self._refresh()
            else:
                self._set_status(verdict.reason, error=True)
            return
        move = self.state.play(row, col)
        self.revision += 1
        self._append_log(
            f"[{STONE_NAME[move.color]} / 人类 / 第 {len(self.state.history)} 手] "
            f"{self._coordinate(row, col)}\n"
        )
        self._set_status(f"玩家落子：{STONE_NAME[move.color]} {self._coordinate(row, col)}")
        self._after_move(auto_continue=True)

    def _start_match(self) -> None:
        if self.busy or self.series_active:
            return
        if self._time_limit(show_error=True) is None:
            return
        missing = [
            STONE_NAME[color]
            for color in self._required_program_colors()
            if not self.players[color].program.is_ready
        ]
        if missing:
            self._set_status(f"请先编译{'、'.join(missing)}方的 C++ 程序。", error=True)
            return

        if self.mode_var.get() == MODE_AI_AI:
            settings = self._series_settings()
            if settings is None:
                return
            self._start_series(*settings)
            return

        self._clear_series()
        self._begin_game()

    def _series_settings(self) -> tuple[int, tuple[float, float, float]] | None:
        try:
            rounds = int(self.rounds_var.get())
        except ValueError:
            self._set_status("对战轮次必须是 1–1000 的整数。", error=True)
            return None
        if not 1 <= rounds <= 1000:
            self._set_status("对战轮次请设在 1–1000 局。", error=True)
            return None
        try:
            points = tuple(
                float(value)
                for value in (
                    self.win_points_var.get(),
                    self.draw_points_var.get(),
                    self.loss_points_var.get(),
                )
            )
        except ValueError:
            self._set_status("胜、和、负积分必须是数字。", error=True)
            return None
        if not all(math.isfinite(value) for value in points):
            self._set_status("积分必须是有限数字。", error=True)
            return None
        win_points, draw_points, loss_points = points
        if not win_points >= draw_points >= loss_points:
            self._set_status("积分需满足：胜分 ≥ 和分 ≥ 负分。", error=True)
            return None
        return rounds, (win_points, draw_points, loss_points)

    def _clear_series(self) -> None:
        self.series_active = False
        self.series_id = ""
        self.series_round = 0
        self.series_total_rounds = 1
        self.series_game_recorded = False
        self.series_scores = {}
        self.series_names = {}
        self.series_first_players = []

    def _start_series(self, rounds: int, points: tuple[float, float, float]) -> None:
        self.series_active = True
        self.series_id = self._new_game_id()
        self.series_round = 0
        self.series_total_rounds = rounds
        self.series_game_recorded = False
        self.series_points = points
        self.series_scores = {
            slot.player_id: SeriesScore() for slot in self.players.values()
        }
        self.series_names = {
            slot.player_id: slot.program.label for slot in self.players.values()
        }
        self.series_first_players = []
        self._append_log(
            f"\n[系列赛 {self.series_id}] 共 {rounds} 局；"
            f"积分（胜/和/负）={points[0]:g}/{points[1]:g}/{points[2]:g}；"
            "每局结束后交换先手。\n"
        )
        self._start_next_series_round(self.series_id)

    def _start_next_series_round(self, series_id: str) -> None:
        if not self.series_active or series_id != self.series_id:
            return
        if self.series_round >= self.series_total_rounds:
            return
        if self.series_round > 0:
            self.players[BLACK], self.players[WHITE] = self.players[WHITE], self.players[BLACK]
        self.series_round += 1
        self._begin_game(
            game_id=f"{self.series_id}-r{self.series_round:03d}",
            series_round=self.series_round,
        )

    def _begin_game(self, *, game_id: str | None = None, series_round: int | None = None) -> None:
        self.state.reset()
        self.game_id = game_id or self._new_game_id()
        self.revision += 1
        self.match_active = True
        self.paused = False
        self.forfeit_color = None
        self.result_detail = ""
        self.series_game_recorded = False
        first_player = self.players[BLACK]
        if series_round is not None:
            self.series_first_players.append(first_player.player_id)
        self._append_log(
            f"\n[新对局 {self.game_id}] 模式：{self._mode_name()}；"
            f"规则：{RULESET_LABELS[self.state.ruleset]}；"
            f"先手：选手 {first_player.player_id}（本局黑方）\n"
        )
        prefix = f"系列赛第 {series_round}/{self.series_total_rounds} 局：" if series_round else ""
        self._set_status(f"{prefix}选手 {first_player.player_id} 先行（黑方）。")
        self._refresh()
        self._advance_turn()

    def _stop_series(self) -> None:
        if not self.series_active or self.busy:
            return
        self.series_active = False
        self.match_active = False
        self.paused = True
        self.revision += 1
        self._append_log("[裁判] 系列赛已由用户终止，未完成局不计分。\n")
        self._set_status("系列赛已终止；已完成局的积分保留在下方。")
        self._refresh()

    def _pause_or_resume(self) -> None:
        if not self.match_active or self._finished():
            return
        if self.paused:
            self.paused = False
            self._set_status("对局继续。")
            self._refresh()
            self._advance_turn()
            return

        self.paused = True
        if self.busy:
            self._set_status("将在当前程序回合结束后暂停。")
        else:
            self._set_status("对局已暂停。")
        self._refresh()

    def _single_step(self) -> None:
        if self.busy or not self.match_active or self._finished():
            return
        color = self.state.side_to_move
        if self.players[color].kind == HUMAN:
            self._set_status(f"当前轮到 {STONE_NAME[color]}方人类，请点击棋盘落子。", error=True)
            return
        self.paused = True
        self._request_program_move(color, auto_continue=False)

    def _undo(self) -> None:
        if self.busy or self.series_active:
            return
        if self.match_active and not self.paused and not self._finished():
            self._set_status("请先暂停对局，再悔棋。", error=True)
            return
        move = self.state.undo()
        if move is None:
            self._set_status("当前没有可悔的棋。", error=True)
            return
        self.revision += 1
        self.match_active = True
        self.paused = True
        self.forfeit_color = None
        self.result_detail = ""
        self._append_log(
            f"[裁判] 撤销 {STONE_NAME[move.color]} {self._coordinate(move.row, move.col)}\n"
        )
        self._set_status("已悔一步；对局保持暂停。")
        self._refresh()

    def _swap_players(self) -> None:
        if self.busy or self.match_active or self.series_active:
            self._set_status("请在开始对局前交换黑白程序。", error=True)
            return
        self.players[BLACK], self.players[WHITE] = self.players[WHITE], self.players[BLACK]
        self._apply_mode()
        self._set_status("黑白方的程序槽位已交换。")
        self._refresh()

    def _choose_source(self, color: int) -> None:
        if self.busy or self.match_active or self.series_active:
            return
        filename = filedialog.askopenfilename(
            parent=self.root,
            title=f"选择{STONE_NAME[color]}方提交的 C++ 单文件",
            filetypes=[("C++ source", "*.cpp *.cc *.cxx *.C"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.players[color].program.select_source(Path(filename))
        self._set_status(f"已选择{STONE_NAME[color]}方源文件；请点击“编译”。")
        self._refresh()

    def _compile_player(self, color: int) -> None:
        if self.busy or (self.match_active and not self.paused):
            return
        program = self.players[color].program
        if program.source_path is None:
            self._set_status(f"请先选择{STONE_NAME[color]}方的 .cpp 文件。", error=True)
            return
        self._set_busy(True, f"正在编译{STONE_NAME[color]}方程序…")

        def work() -> None:
            self.jobs.put(("compile", color, program.compile()))

        threading.Thread(target=work, daemon=True).start()

    def _advance_turn(self) -> None:
        if self.busy or self.paused or not self.match_active or self._finished():
            return
        color = self.state.side_to_move
        if self.players[color].kind == HUMAN:
            self._set_status(f"轮到 {STONE_NAME[color]}方玩家落子。")
            self._refresh()
            return
        self._request_program_move(color, auto_continue=True)

    def _request_program_move(self, color: int, *, auto_continue: bool) -> None:
        if self.busy or self._finished() or self.state.side_to_move != color:
            return
        request = self._current_request(show_error=True)
        if request is None:
            return
        program = self.players[color].program
        game_id = self.game_id
        revision = self.revision
        strict_case_id = self.mode_var.get() == MODE_AI_AI
        self._set_busy(True, f"正在请求{STONE_NAME[color]}方程序 {program.label} 落子…")

        def work() -> None:
            result = program.run_one_move(
                request,
                request["rules"]["time_limit_ms"],
                require_case_id=strict_case_id,
            )
            self.jobs.put(("move", color, game_id, revision, auto_continue, program.label, result))

        threading.Thread(target=work, daemon=True).start()

    def _poll_jobs(self) -> None:
        try:
            while True:
                item = self.jobs.get_nowait()
                kind = item[0]
                if kind == "compile":
                    _, color, result = item
                    ok, message = result
                    self._append_log(f"[{STONE_NAME[color]} / 编译]\n{message}\n")
                    self._set_busy(False)
                    self._set_status(
                        f"{STONE_NAME[color]}方程序编译成功。" if ok else f"{STONE_NAME[color]}方程序编译失败。",
                        error=not ok,
                    )
                    self._refresh()
                elif kind == "move":
                    _, color, game_id, revision, auto_continue, program_label, result = item
                    ok, message, response = result
                    self._set_busy(False)
                    if game_id != self.game_id or revision != self.revision or color != self.state.side_to_move:
                        self._append_log(f"[{STONE_NAME[color]} / {program_label}] 已丢弃过期响应。\n")
                        self._refresh()
                        continue

                    self._append_log(
                        f"[{STONE_NAME[color]} / {program_label} / 第 {len(self.state.history) + 1} 手]\n"
                        f"{message}\n"
                    )
                    if not ok or response is None:
                        self._handle_program_failure(color, message.splitlines()[0] or "程序未给出有效落子")
                        self._refresh()
                        continue

                    row, col = response["move"]
                    verdict = self.state.analyze_move(row, col)
                    if not verdict.legal:
                        if verdict.forbidden is not None:
                            self._declare_forfeit(color, verdict.reason)
                        else:
                            self._handle_program_failure(
                                color, f"非法落子 [{row},{col}]：{verdict.reason}"
                            )
                        self._refresh()
                        continue

                    move = self.state.play(row, col)
                    self.revision += 1
                    self._set_status(
                        f"{STONE_NAME[move.color]}方程序落子：{self._coordinate(row, col)}"
                    )
                    self._after_move(auto_continue=auto_continue)
        except queue.Empty:
            pass
        self.root.after(60, self._poll_jobs)

    def _handle_program_failure(self, color: int, reason: str) -> None:
        if self.mode_var.get() == MODE_AI_AI:
            self._declare_forfeit(color, reason)
        else:
            self.paused = True
            self._set_status(f"{STONE_NAME[color]}方程序出错：{reason}。已暂停，可修正后单步重试。", error=True)

    def _record_series_result(self) -> None:
        """仅为已结束的一盘 AI vs AI 计分，并安排下一盘的先手交换。"""
        if not self.series_active or self.series_game_recorded:
            return
        self.series_game_recorded = True
        black_id = self.players[BLACK].player_id
        white_id = self.players[WHITE].player_id
        black_score = self.series_scores[black_id]
        white_score = self.series_scores[white_id]
        win_points, draw_points, loss_points = self.series_points

        winner = self.state.winner
        if self.forfeit_color is not None:
            winner = WHITE if self.forfeit_color == BLACK else BLACK
        if winner == EMPTY:
            for score in (black_score, white_score):
                score.games += 1
                score.draws += 1
                score.points += draw_points
            outcome = "和棋"
        else:
            winner_id = self.players[winner].player_id
            loser = WHITE if winner == BLACK else BLACK
            winner_score = self.series_scores[winner_id]
            loser_score = self.series_scores[self.players[loser].player_id]
            winner_score.games += 1
            winner_score.wins += 1
            winner_score.points += win_points
            loser_score.games += 1
            loser_score.losses += 1
            loser_score.points += loss_points
            outcome = f"选手 {winner_id} 获胜"

        self._append_log(
            f"[系列赛] 第 {self.series_round} 局：{outcome}；{self._series_summary()}\n"
        )
        if self.series_round >= self.series_total_rounds:
            self.series_active = False
            self._set_status(f"系列赛结束。{self._series_summary()}")
            return

        self._set_status(
            f"第 {self.series_round} 局结束（{outcome}）；即将交换先手，开始下一局。"
        )
        series_id = self.series_id
        self.root.after(
            AUTO_STEP_DELAY_MS * 2,
            lambda: self._start_next_series_round(series_id),
        )

    def _declare_forfeit(self, color: int, reason: str) -> None:
        self.forfeit_color = color
        self.result_detail = reason
        self.match_active = False
        self.paused = False
        self._set_status(self._result_text(), error=True)
        self._append_log(f"[裁判] {STONE_NAME[color]}方判负：{reason}\n")
        self._record_series_result()

    def _after_move(self, *, auto_continue: bool) -> None:
        if self.state.winner or self.state.is_draw():
            self.match_active = False
            self.paused = False
            self._set_status(self._result_text())
            self._record_series_result()
            self._refresh()
            return

        if not auto_continue:
            self.paused = True
            self._set_status("已完成一个 AI 单步；对局保持暂停。")
            self._refresh()
            return

        self._refresh()
        self.root.after(AUTO_STEP_DELAY_MS, self._advance_turn)

    def _copy_request(self) -> None:
        request = self._current_request(show_error=True)
        if request is None:
            return
        text = json.dumps(request, ensure_ascii=False, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("当前 Request 已复制到剪贴板。")

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self.busy = busy
        if status:
            self._set_status(status)
        self._refresh_controls()

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_var.set(("错误：" if error else "") + message)

    @staticmethod
    def _set_text(widget: scrolledtext.ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _coordinate(row: int, col: int) -> str:
        return f"{chr(ord('A') + col)}{row + 1}（[{row},{col}]）"

    @staticmethod
    def _new_game_id() -> str:
        return uuid.uuid4().hex[:8]

    def _mode_name(self) -> str:
        return {
            MODE_HUMAN_AI: "玩家 vs C++",
            MODE_AI_AI: "C++ vs C++",
            MODE_DEBUG: "自由摆棋",
        }[self.mode_var.get()]

    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno("正在运行", "学生程序仍在运行。确定退出吗？", parent=self.root):
            return
        for slot in self.players.values():
            slot.program.close()
        self.root.destroy()


def main() -> None:
    root = Tk()
    GomokuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
