#!/usr/bin/env python3
"""五子棋助教端界面原型。

学生只提交一个 C++ 源文件。界面负责：编译源文件、把当前棋盘作为一行 JSON
写入学生程序 stdin，并读取它输出的一行 JSON 落子结果。

这是一个本地原型，依赖仅为 Python 标准库和 tkinter。
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, messagebox, scrolledtext, ttk
import tkinter as tk
from typing import Any


EMPTY = 0
BLACK = 1
WHITE = 2
BOARD_SIZE = 15
WIN_LENGTH = 5
STONE_NAME = {BLACK: "黑", WHITE: "白"}


@dataclass(frozen=True)
class Move:
    row: int
    col: int
    color: int


@dataclass
class GomokuState:
    """界面唯一持有的可信棋局状态。学生程序只给出候选落子。"""

    board: list[list[int]] = field(
        default_factory=lambda: [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    )
    side_to_move: int = BLACK
    last_move: Move | None = None
    history: list[Move] = field(default_factory=list)
    winner: int = EMPTY

    def reset(self) -> None:
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.side_to_move = BLACK
        self.last_move = None
        self.history.clear()
        self.winner = EMPTY

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def is_legal(self, row: int, col: int) -> bool:
        return self.winner == EMPTY and self.in_bounds(row, col) and self.board[row][col] == EMPTY

    def play(self, row: int, col: int) -> Move:
        if not self.is_legal(row, col):
            raise ValueError("落子越界、位置已有棋子，或对局已结束")
        move = Move(row, col, self.side_to_move)
        self.board[row][col] = move.color
        self.history.append(move)
        self.last_move = move
        if self._has_five(row, col, move.color):
            self.winner = move.color
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
        return self.winner == EMPTY and len(self.history) == BOARD_SIZE * BOARD_SIZE

    def _has_five(self, row: int, col: int, color: int) -> bool:
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for sign in (-1, 1):
                r, c = row + sign * dr, col + sign * dc
                while self.in_bounds(r, c) and self.board[r][c] == color:
                    count += 1
                    r += sign * dr
                    c += sign * dc
            if count >= WIN_LENGTH:
                return True
        return False

    def request(self, case_id: str, time_limit_ms: int) -> dict[str, Any]:
        return {
            "protocol_version": "gomoku-1.0",
            "case_id": case_id,
            "board_size": BOARD_SIZE,
            "board": self.board,
            "side_to_move": self.side_to_move,
            "last_move": (
                [self.last_move.row, self.last_move.col] if self.last_move is not None else None
            ),
            "rules": {
                "win_length": WIN_LENGTH,
                "forbidden_moves": "none",
                "time_limit_ms": time_limit_ms,
            },
        }


class StudentProgram:
    """将学生的一份 C++ 单文件编译成独立程序，并按一手一进程调用。"""

    def __init__(self) -> None:
        self.source_path: Path | None = None
        self.executable_path: Path | None = None
        self.build_dir = Path(tempfile.mkdtemp(prefix="gomoku-student-"))

    @staticmethod
    def find_compiler() -> str | None:
        configured = os.environ.get("CXX")
        if configured and shutil.which(configured):
            return configured
        return shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")

    def compile(self, source_path: Path) -> tuple[bool, str]:
        compiler = self.find_compiler()
        if compiler is None:
            return False, "未找到 C++ 编译器。请安装或把 CXX 指向 c++ / g++ / clang++。"

        suffix = ".exe" if os.name == "nt" else ""
        executable = self.build_dir / f"student_solver{suffix}"
        command = [compiler, "-std=c++17", "-O2", str(source_path), "-o", str(executable)]
        try:
            result = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "编译超过 20 秒，已停止。"
        except OSError as error:
            return False, f"无法启动编译器：{error}"

        compiler_text = (result.stdout + result.stderr).strip()
        if result.returncode != 0 or not executable.exists():
            detail = compiler_text or f"编译失败（退出码 {result.returncode}）"
            return False, detail

        self.source_path = source_path
        self.executable_path = executable
        return True, compiler_text or "编译成功。"

    def run_one_move(self, request: dict[str, Any], timeout_ms: int) -> tuple[bool, str, dict[str, Any] | None]:
        if self.executable_path is None:
            return False, "请先选择并编译学生的 C++ 源文件。", None

        stdin_text = json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            process = subprocess.Popen(
                [str(self.executable_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(stdin_text, timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return False, f"程序超过 {timeout_ms} ms，已停止。\nstderr:\n{stderr.strip()}", None
        except OSError as error:
            return False, f"无法启动学生程序：{error}", None

        stderr_text = stderr.strip()
        if process.returncode != 0:
            return False, f"学生程序异常退出（退出码 {process.returncode}）。\nstderr:\n{stderr_text}", None

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
        if response.get("case_id") not in (None, request["case_id"]):
            return False, "Response 的 case_id 与 Request 不匹配。", None
        if "move" not in response:
            return False, "Response 缺少 move；规范格式为 {\"move\":[row,col]}。", None
        move = response["move"]
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

    def close(self) -> None:
        shutil.rmtree(self.build_dir, ignore_errors=True)


class GomokuApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("五子棋助教端原型")
        self.root.minsize(980, 720)
        self.root.geometry("1220x820")

        self.state = GomokuState()
        self.student = StudentProgram()
        self.jobs: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.case_number = 0
        self.board_margin = 42.0
        self.board_cell = 40.0
        self.board_origin = (42.0, 42.0)

        self.status_var = StringVar(value="黑方先行：点击棋盘手动落子，或先构造局面再调用学生程序。")
        self.source_var = StringVar(value="未选择 C++ 源文件")
        self.time_limit_var = StringVar(value="2000")
        self.turn_var = StringVar()
        self.position_var = StringVar()
        self._build_ui()
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll_jobs)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Helvetica", 16, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 11, "bold"))

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)
        outer.rowconfigure(1, weight=1)

        ttk.Label(outer, text="五子棋 · 人机对弈验收原型", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").grid(
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
        ttk.Button(controls, text="新对局", command=self._new_game).pack(side="left")
        ttk.Button(controls, text="悔一步", command=self._undo).pack(side="left", padx=6)
        self.run_button = ttk.Button(controls, text="让学生程序走当前方", command=self._run_student)
        self.run_button.pack(side="left")
        ttk.Button(controls, text="复制当前 Request", command=self._copy_request).pack(side="right")

        side = ttk.Frame(outer, width=370)
        side.grid(row=1, column=1, sticky="ns", padx=(14, 0), pady=(12, 0))
        side.grid_propagate(False)

        submission = ttk.LabelFrame(side, text="学生单文件程序", padding=10)
        submission.pack(fill="x")
        ttk.Label(submission, textvariable=self.source_var, wraplength=330).pack(anchor="w")
        submission_buttons = ttk.Frame(submission)
        submission_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(submission_buttons, text="选择 .cpp", command=self._choose_source).pack(side="left")
        self.compile_button = ttk.Button(submission_buttons, text="编译", command=self._compile_student)
        self.compile_button.pack(side="left", padx=6)
        ttk.Label(submission_buttons, text="单步限时 (ms)").pack(side="left", padx=(12, 4))
        ttk.Entry(submission_buttons, textvariable=self.time_limit_var, width=7).pack(side="left")

        state_box = ttk.LabelFrame(side, text="棋局", padding=10)
        state_box.pack(fill="x", pady=(10, 0))
        ttk.Label(state_box, textvariable=self.turn_var).pack(anchor="w")
        ttk.Label(state_box, textvariable=self.position_var).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            state_box,
            text="坐标采用 0-based [row,col]；棋盘上显示 A–O 与 1–15。",
            foreground="#555555",
            wraplength=330,
        ).pack(anchor="w", pady=(7, 0))

        request_box = ttk.LabelFrame(side, text="发给学生程序的 Request", padding=6)
        request_box.pack(fill="both", expand=True, pady=(10, 0))
        self.request_text = scrolledtext.ScrolledText(
            request_box, height=11, wrap="word", font=("Menlo", 10), state="disabled"
        )
        self.request_text.pack(fill="both", expand=True)

        log_box = ttk.LabelFrame(side, text="编译 / 程序日志", padding=6)
        log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(
            log_box, height=11, wrap="word", font=("Menlo", 10), state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

    def _time_limit(self) -> int | None:
        try:
            value = int(self.time_limit_var.get())
        except ValueError:
            self._set_status("单步限时必须是正整数。", error=True)
            return None
        if not 50 <= value <= 60_000:
            self._set_status("单步限时请设在 50–60000 ms。", error=True)
            return None
        return value

    def _request(self) -> dict[str, Any] | None:
        limit = self._time_limit()
        if limit is None:
            return None
        return self.state.request(f"live-{self.case_number:04d}", limit)

    def _refresh(self) -> None:
        if self.state.winner:
            self.turn_var.set(f"对局结束：{STONE_NAME[self.state.winner]}方五连获胜")
        elif self.state.is_draw():
            self.turn_var.set("对局结束：和棋")
        else:
            self.turn_var.set(f"轮到 {STONE_NAME[self.state.side_to_move]}方落子")

        last = "无"
        if self.state.last_move:
            last = f"{STONE_NAME[self.state.last_move.color]} {self._coordinate(self.state.last_move.row, self.state.last_move.col)}"
        self.position_var.set(f"已落 {len(self.state.history)} 手；上一手：{last}")
        request = self._request()
        if request is not None:
            self._set_text(self.request_text, json.dumps(request, ensure_ascii=False, indent=2))
        self._draw_board()

    def _draw_board(self) -> None:
        canvas = self.board_canvas
        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 200)
        margin = max(28.0, min(width, height) * 0.065)
        cell = (min(width, height) - 2 * margin) / (BOARD_SIZE - 1)
        board_pixels = cell * (BOARD_SIZE - 1)
        x0 = (width - board_pixels) / 2
        y0 = (height - board_pixels) / 2
        self.board_margin = margin
        self.board_cell = cell
        self.board_origin = (x0, y0)

        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#e6bd75", outline="")
        for index in range(BOARD_SIZE):
            x = x0 + index * cell
            y = y0 + index * cell
            canvas.create_line(x0, y, x0 + board_pixels, y, fill="#4c3720", width=1)
            canvas.create_line(x, y0, x, y0 + board_pixels, fill="#4c3720", width=1)
            canvas.create_text(x, y0 - 18, text=chr(ord("A") + index), fill="#4c3720", font=("Helvetica", 10))
            canvas.create_text(x0 - 18, y, text=str(index + 1), fill="#4c3720", font=("Helvetica", 10))

        star_radius = max(2, cell * 0.07)
        for row, col in ((3, 3), (3, 11), (7, 7), (11, 3), (11, 11)):
            x, y = x0 + col * cell, y0 + row * cell
            canvas.create_oval(x - star_radius, y - star_radius, x + star_radius, y + star_radius, fill="#49331d", outline="")

        radius = cell * 0.43
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
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
        x0, y0 = self.board_origin
        col = round((event.x - x0) / self.board_cell)
        row = round((event.y - y0) / self.board_cell)
        x = x0 + col * self.board_cell
        y = y0 + row * self.board_cell
        if not self.state.in_bounds(row, col) or abs(event.x - x) > self.board_cell * 0.45 or abs(event.y - y) > self.board_cell * 0.45:
            return
        try:
            move = self.state.play(row, col)
        except ValueError as error:
            self._set_status(str(error), error=True)
            return
        self.case_number += 1
        self._set_status(f"手动落子：{STONE_NAME[move.color]} {self._coordinate(row, col)}")
        self._refresh()

    def _new_game(self) -> None:
        if self.busy:
            return
        self.state.reset()
        self.case_number += 1
        self._set_status("新对局已开始：黑方先行。")
        self._refresh()

    def _undo(self) -> None:
        if self.busy:
            return
        move = self.state.undo()
        if move is None:
            self._set_status("当前没有可悔的棋。", error=True)
            return
        self.case_number += 1
        self._set_status(f"已撤销 {STONE_NAME[move.color]} {self._coordinate(move.row, move.col)}")
        self._refresh()

    def _choose_source(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="选择学生提交的 C++ 单文件",
            filetypes=[("C++ source", "*.cpp *.cc *.cxx *.C"), ("All files", "*.*")],
        )
        if not filename:
            return
        path = Path(filename)
        self.student.source_path = path
        self.student.executable_path = None
        self.source_var.set(str(path))
        self._set_status("已选择源文件；请点击“编译”。")

    def _compile_student(self) -> None:
        if self.busy:
            return
        source = self.student.source_path
        if source is None:
            self._set_status("请先选择学生的 .cpp 文件。", error=True)
            return
        self._set_busy(True, "正在编译学生程序…")

        def work() -> None:
            self.jobs.put(("compile", self.student.compile(source)))

        threading.Thread(target=work, daemon=True).start()

    def _run_student(self) -> None:
        if self.busy:
            return
        if self.state.winner or self.state.is_draw():
            self._set_status("对局已结束；请新开对局或悔棋。", error=True)
            return
        request = self._request()
        if request is None:
            return
        self._set_busy(True, f"正在请求学生程序为 {STONE_NAME[self.state.side_to_move]}方落子…")

        def work() -> None:
            self.jobs.put(("run", self.student.run_one_move(request, request["rules"]["time_limit_ms"]), request))

        threading.Thread(target=work, daemon=True).start()

    def _poll_jobs(self) -> None:
        try:
            while True:
                item = self.jobs.get_nowait()
                kind = item[0]
                if kind == "compile":
                    ok, message = item[1]
                    self._append_log(f"[编译]\n{message}\n")
                    self._set_busy(False)
                    self._set_status("编译成功，可以调用程序。" if ok else "编译失败，请查看日志。", error=not ok)
                elif kind == "run":
                    ok, message, response = item[1]
                    self._append_log(f"[第 {len(self.state.history) + 1} 手]\n{message}\n")
                    self._set_busy(False)
                    if not ok or response is None:
                        self._set_status("学生程序未给出有效落子，请查看日志。", error=True)
                    else:
                        row, col = response["move"]
                        if not self.state.is_legal(row, col):
                            self._set_status(
                                f"程序返回非法落子 [{row},{col}]，已拒绝执行。", error=True
                            )
                        else:
                            move = self.state.play(row, col)
                            self.case_number += 1
                            self._set_status(
                                f"学生程序已落子：{STONE_NAME[move.color]} {self._coordinate(row, col)}"
                            )
                    self._refresh()
        except queue.Empty:
            pass
        self.root.after(60, self._poll_jobs)

    def _copy_request(self) -> None:
        request = self._request()
        if request is None:
            return
        text = json.dumps(request, ensure_ascii=False, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("当前 Request 已复制到剪贴板。")

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.run_button.configure(state=state)
        self.compile_button.configure(state=state)
        if status:
            self._set_status(status)

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

    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno("正在运行", "学生程序仍在运行。确定退出吗？", parent=self.root):
            return
        self.student.close()
        self.root.destroy()


def main() -> None:
    root = Tk()
    GomokuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
