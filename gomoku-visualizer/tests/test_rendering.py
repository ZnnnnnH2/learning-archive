import sys
import tkinter as tk
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gobang_gui import (  # noqa: E402
    GomokuApp,
    GomokuState,
    RULE_FREESTYLE,
)


class RecordingCanvas:
    """够用的 Canvas 替身：验证渲染增量而不启动 Tk 窗口。"""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.ovals: list[tuple[tuple[object, ...], dict[str, object]]] = []

    @staticmethod
    def winfo_width() -> int:
        return 600

    @staticmethod
    def winfo_height() -> int:
        return 600

    def delete(self, tag: str) -> None:
        self.deleted.append(tag)

    def create_rectangle(self, *_args: object, **_kwargs: object) -> None:
        pass

    def create_line(self, *_args: object, **_kwargs: object) -> None:
        pass

    def create_text(self, *_args: object, **_kwargs: object) -> None:
        pass

    def create_oval(self, *args: object, **kwargs: object) -> None:
        self.ovals.append((args, kwargs))

    def clear_changes(self) -> None:
        self.deleted.clear()
        self.ovals.clear()


class BoardRenderingTests(unittest.TestCase):
    def make_app(self) -> tuple[GomokuApp, RecordingCanvas]:
        app = GomokuApp.__new__(GomokuApp)
        app.state = GomokuState(board_size=9, ruleset=RULE_FREESTYLE)
        canvas = RecordingCanvas()
        app.board_canvas = canvas
        app.board_cell = 0.0
        app.board_origin = (0.0, 0.0)
        app._board_layout = None
        app._rendered_board = None
        app._rendered_last_move = None
        return app, canvas

    def test_unchanged_board_is_not_redrawn_and_new_move_is_incremental(self) -> None:
        app, canvas = self.make_app()
        app.state.play(4, 4)
        app._draw_board()

        canvas.clear_changes()
        app._draw_board()
        self.assertEqual(canvas.deleted, [])
        self.assertEqual(canvas.ovals, [])

        app.state.play(0, 0)
        app._draw_board()
        self.assertEqual(canvas.deleted, ["stone-0-0", "last-move"])
        # 仅新增的白棋与移动后的上一手标记；既有黑棋没有被删除重画。
        self.assertEqual(len(canvas.ovals), 2)
        self.assertNotIn("all", canvas.deleted)
        self.assertNotIn("stone", canvas.deleted)


class LayoutStabilityTests(unittest.TestCase):
    """使用真实 Tk 几何计算验证动态文本不会再挤压棋盘。"""

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"当前环境无法启动 Tk：{error}")
        self.root.withdraw()
        self.app = GomokuApp(self.root)
        self.root.update_idletasks()

    def tearDown(self) -> None:
        if hasattr(self, "root"):
            self.root.destroy()

    def layout_snapshot(self) -> tuple[tuple[int, int], ...]:
        self.root.update_idletasks()
        return (
            (self.root.winfo_reqwidth(), self.root.winfo_reqheight()),
            (self.app.sidebar.winfo_width(), self.app.sidebar.winfo_height()),
            (self.app.board_area.winfo_width(), self.app.board_area.winfo_height()),
            (self.app.board_canvas.winfo_width(), self.app.board_canvas.winfo_height()),
        )

    def test_dynamic_game_text_does_not_resize_sidebar_or_board(self) -> None:
        expected = self.layout_snapshot()
        for row, col in (self.app.state.opening_center, (0, 0), (0, 1), (1, 0)):
            self.app.state.play(row, col)
            self.app._refresh()
            self.assertEqual(self.layout_snapshot(), expected)

        self.app.position_var.set("很长的动态棋局说明" * 20)
        self.app.series_summary_var.set("很长的系列赛结果" * 20)
        self.app.status_var.set("很长的顶部状态" * 20)
        self.assertEqual(self.layout_snapshot(), expected)

    def test_debug_tabs_receive_the_remaining_sidebar_space(self) -> None:
        self.app.sidebar_notebook.select(1)
        self.root.update_idletasks()
        self.assertGreater(self.app.debug_notebook.winfo_width(), 300)
        self.assertGreater(self.app.debug_notebook.winfo_height(), 300)

    def test_identical_request_is_not_rewritten(self) -> None:
        writes: list[str] = []
        self.app._request_text_cache = None
        self.app._set_text = lambda _widget, text: writes.append(text)  # type: ignore[method-assign]

        self.app._refresh()
        self.app._refresh()
        self.assertEqual(len(writes), 1)

        self.app.state.play(*self.app.state.opening_center)
        self.app._refresh()
        self.assertEqual(len(writes), 2)


if __name__ == "__main__":
    unittest.main()
