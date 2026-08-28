import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gobang_gui import (  # noqa: E402
    BLACK,
    MODE_AI_AI,
    WHITE,
    GomokuApp,
    GomokuState,
    PlayerSlot,
    RULE_RENJU_CLASSROOM,
    SeriesScore,
    StudentProgram,
)


class Value:
    """无需启动 Tk 窗口的 StringVar 替身。"""

    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class SeriesMatchTests(unittest.TestCase):
    """验证系列赛换先、可调试 stdout 与记录回放的非图形逻辑。"""

    @classmethod
    def setUpClass(cls) -> None:
        if StudentProgram.find_compiler() is None:
            raise unittest.SkipTest("本机没有可用的 C++ 编译器")

    def headless_app(self) -> GomokuApp:
        app = GomokuApp.__new__(GomokuApp)
        app.mode_var = Value(MODE_AI_AI)
        app.ruleset_var = Value(RULE_RENJU_CLASSROOM)
        app.board_size_var = Value("9")
        app.state = GomokuState(board_size=9, ruleset=RULE_RENJU_CLASSROOM)
        app.players = {BLACK: PlayerSlot("A"), WHITE: PlayerSlot("B")}
        app.game_id = "replay-case"
        app.forfeit_color = None
        app.result_detail = ""
        app.revision = 0
        app.replay = None
        app.replay_autoplay = False
        app.match_active = False
        app.paused = False
        app.series_active = False
        app.series_id = ""
        app.series_round = 0
        app.series_total_rounds = 1
        app.series_game_recorded = False
        app.series_scores = {}
        app.series_names = {}
        app.series_first_players = []
        app._append_log = lambda _text: None
        app._set_status = lambda _message, error=False: None
        app._refresh = lambda: None
        return app

    def test_program_accepts_extra_stdout_debug_output(self) -> None:
        program = StudentProgram()
        self.addCleanup(program.close)
        source = Path(__file__).parent / "fixtures" / "forfeit_after_opening.cpp"
        program.select_source(source)
        ok, log = program.compile()
        self.assertTrue(ok, log)

        request = GomokuState(board_size=9).request("debug-output", 2000)
        ok, log, response = program.run_one_move(request, 2000, require_case_id=True)
        self.assertTrue(ok, log)
        self.assertEqual(response["move"], [4, 4])
        self.assertIn("stdout 调试输出:\ndebug: received ply=0", log)
        self.assertIn("debug: response emitted", log)

    def test_series_swaps_first_player_every_round(self) -> None:
        app = self.headless_app()
        app.series_active = True
        app.series_id = "series"
        app.series_total_rounds = 2
        started: list[tuple[str, int]] = []
        app._begin_game = lambda **kwargs: started.append(
            (app.players[BLACK].player_id, kwargs["series_round"])
        )

        app._start_next_series_round("series")
        app._start_next_series_round("series")

        self.assertEqual(started, [("A", 1), ("B", 2)])

    def test_series_score_tracks_stable_player_ids_after_forfeit(self) -> None:
        app = self.headless_app()
        app.state.play(4, 4)
        app.series_active = True
        app.series_round = 1
        app.series_total_rounds = 1
        app.series_points = (3.0, 1.0, 0.0)
        app.series_scores = {"A": SeriesScore(), "B": SeriesScore()}
        app.series_names = {"A": "a.cpp", "B": "b.cpp"}
        app.forfeit_color = WHITE
        app.result_detail = "测试判负"

        app._record_series_result()

        self.assertFalse(app.series_active)
        self.assertEqual((app.series_scores["A"].wins, app.series_scores["A"].points), (1, 3))
        self.assertEqual((app.series_scores["B"].losses, app.series_scores["B"].points), (1, 0))

    def test_exported_payload_replays_one_move_at_a_time(self) -> None:
        app = self.headless_app()
        app.state.play(4, 4)
        app.state.play(0, 0)
        payload = app._record_payload()
        replay = app._parse_replay_record(payload, Path("sample-game.json"))

        app._start_replay(replay)
        self.assertEqual(len(app.state.history), 0)
        app._replay_next()
        self.assertEqual([(move.row, move.col) for move in app.state.history], [(4, 4)])
        app._replay_next()
        self.assertEqual([(move.row, move.col) for move in app.state.history], [(4, 4), (0, 0)])
        self.assertEqual(app.replay.cursor, 2)


if __name__ == "__main__":
    unittest.main()
