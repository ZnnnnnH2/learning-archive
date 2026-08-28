import sys
import time
import tkinter as tk
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gobang_gui import BLACK, MODE_AI_AI, WHITE, GomokuApp, StudentProgram  # noqa: E402


class SeriesMatchTests(unittest.TestCase):
    """通过真实 C++ 程序验证系列赛的换先与积分。"""

    @classmethod
    def setUpClass(cls) -> None:
        if StudentProgram.find_compiler() is None:
            raise unittest.SkipTest("本机没有可用的 C++ 编译器")

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = GomokuApp(self.root)
        self.app.mode_var.set(MODE_AI_AI)
        self.app._on_mode_changed()
        self.app.board_size_var.set("9")
        self.app._on_board_size_changed()
        self.assertEqual(self.app.state.board_size, 9)
        source = Path(__file__).parent / "fixtures" / "forfeit_after_opening.cpp"
        for color in (BLACK, WHITE):
            program = self.app.players[color].program
            program.select_source(source)
            ok, log = program.compile()
            self.assertTrue(ok, log)

    def tearDown(self) -> None:
        for slot in self.app.players.values():
            slot.program.close()
        self.root.destroy()

    def test_two_rounds_swap_first_player_and_score_by_player(self) -> None:
        self.app.rounds_var.set("2")
        self.app.win_points_var.set("3")
        self.app.draw_points_var.set("1")
        self.app.loss_points_var.set("0")
        self.app._start_match()

        deadline = time.monotonic() + 10
        while self.app.series_active and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()

        self.assertFalse(self.app.series_active, "系列赛没有在限定时间内结束")
        self.assertEqual(self.app.series_first_players, ["A", "B"])
        for player_id in ("A", "B"):
            score = self.app.series_scores[player_id]
            self.assertEqual((score.games, score.wins, score.draws, score.losses), (2, 1, 0, 1))
            self.assertEqual(score.points, 3)


if __name__ == "__main__":
    unittest.main()
