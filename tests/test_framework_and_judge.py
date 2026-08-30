from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gomoku_display.framework import freeze_framework, legal_from_course
from gomoku_display.judge import Judge, replay_game
from gomoku_display.runner import TurnOutput
from gomoku_display.store import EventStore
from gomoku_display.tournament import round_robin
from gomoku_display.openings import OPENINGS

SOURCE = Path("/Users/hanyuhe/Desktop/gomoku")


class TimeoutRunner:
    def turn(self, binary: Path, position: str) -> TurnOutput:
        return TurnOutput(124, "", "", True)


class FrameworkAndJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        freeze_framework(SOURCE, self.data)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_course_library_basics_and_exact_five_priority(self) -> None:
        empty = ["." * 15 for _ in range(15)]
        self.assertEqual(legal_from_course(self.data, empty, -1, 0, "W")["status"], "OUT_OF_BOUNDS")
        board = [list("." * 15) for _ in range(15)]
        for x in range(4): board[7][x] = "B"
        result = legal_from_course(self.data, ["".join(row) for row in board], 4, 7, "B")
        self.assertTrue(result["legal"])
        self.assertEqual(result["result_after"], "BLACK_WIN")

    def test_course_regression_cases_and_openings(self) -> None:
        def board_with(points: list[tuple[int, int]]) -> list[str]:
            board = [list("." * 15) for _ in range(15)]
            for x, y in points: board[y][x] = "B"
            return ["".join(row) for row in board]
        occupied = board_with([(7, 7)])
        self.assertEqual(legal_from_course(self.data, occupied, 7, 7, "B")["status"], "OCCUPIED")
        overline = board_with([(x, 0) for x in range(5)])
        self.assertEqual(legal_from_course(self.data, overline, 5, 0, "B")["status"], "OVERLINE")
        four_four = board_with([(x, 7) for x in range(4, 7)] + [(7, y) for y in range(4, 7)])
        self.assertEqual(legal_from_course(self.data, four_four, 7, 7, "B")["status"], "DOUBLE_FOUR")
        three_three = board_with([(6, 7), (8, 7), (7, 6), (7, 8)])
        self.assertEqual(legal_from_course(self.data, three_three, 7, 7, "B")["status"], "DOUBLE_THREE")
        # The same local pattern must keep its verdict under every board symmetry.
        from gomoku_display.openings import apply_symmetry
        for symmetry in range(8):
            transformed = [list("." * 15) for _ in range(15)]
            for x, y in [(6, 7), (8, 7), (7, 6), (7, 8)]:
                tx, ty = apply_symmetry(x, y, symmetry); transformed[ty][tx] = "B"
            tx, ty = apply_symmetry(7, 7, symmetry)
            self.assertEqual(legal_from_course(self.data, ["".join(row) for row in transformed], tx, ty, "B")["status"],
                             "DOUBLE_THREE")
        for opening in OPENINGS:
            for symmetry in range(8):
                board = [list("." * 15) for _ in range(15)]
                for ply, (x, y) in enumerate(opening.moves(symmetry)):
                    color = "B" if ply % 2 == 0 else "W"
                    self.assertTrue(legal_from_course(self.data, ["".join(row) for row in board], x, y, color)["legal"])
                    board[y][x] = color

    def test_timeout_is_recorded_and_replay_is_readonly(self) -> None:
        store = EventStore(self.data)
        store.replace_roster([("1", "甲"), ("2", "乙")])
        for student in ("1", "2"):
            source = self.data / f"{student}.cpp"; source.write_text("// test")
            store.upsert_submission(student, str(source), "x", "READY", binary_path=str(source))
        pairing = round_robin("A", ["1", "2", "3", "4", "5", "6"])[0]
        # Insert only a single pairing/game without draw; this keeps the test focused on the game loop.
        with store.connection:
            store.connection.execute("INSERT INTO tournament(id,seed,phase,manifest_json) VALUES(1,1,'GROUP','{}')")
            cursor = store.connection.execute("""INSERT INTO pairing(stage,group_name,round_no,board_no,left_id,right_id,opening_id,symmetry)
                VALUES('GROUP','A',1,1,'1','2',1,0)""")
            store.connection.execute("INSERT INTO game(pairing_id,game_no,black_id,white_id) VALUES(?,?,?,?)",
                                     (cursor.lastrowid, 1, "1", "2"))
        result = Judge(store, self.data, TimeoutRunner()).run_game(1)
        self.assertEqual(result, "TURN_TIMEOUT")
        game = store.game(1)
        self.assertEqual(game["winner_id"], "1")  # opening ends with black, so white moves first and times out.
        replay = replay_game(store, self.data, 1)
        self.assertTrue(replay["ok"])
        self.assertEqual(len(replay["moves"]), 0)
        store.close()
