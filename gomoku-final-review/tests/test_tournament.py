from __future__ import annotations

import unittest

from gomoku_display.openings import OPENINGS
from gomoku_display.tournament import GameScore, draw_groups, round_robin, standings


class TournamentTests(unittest.TestCase):
    def test_official_openings_and_all_symmetries_fit_board(self) -> None:
        self.assertEqual(len(OPENINGS), 12)
        for opening in OPENINGS:
            self.assertEqual(len(opening.relative_moves), 5)
            for symmetry in range(8):
                moves = opening.moves(symmetry)
                self.assertEqual(len(set(moves)), 5)
                self.assertTrue(all(0 <= x < 15 and 0 <= y < 15 for x, y in moves))
                self.assertEqual(moves[0], (7, 7))

    def test_21_player_draw_and_circle_schedule(self) -> None:
        groups = draw_groups([f"2026{i:04d}" for i in range(21)], 123456)
        self.assertEqual({name: len(members) for name, members in groups.items()},
                         {"A": 6, "B": 5, "C": 5, "D": 5})
        all_pairs = 0
        for name, members in groups.items():
            schedule = round_robin(name, members)
            self.assertEqual({item.round for item in schedule}, {1, 2, 3, 4, 5})
            expected = len(members) * (len(members) - 1) // 2
            self.assertEqual(len(schedule), expected)
            self.assertEqual(len({tuple(sorted((item.left, item.right))) for item in schedule}), expected)
            all_pairs += len(schedule)
        self.assertEqual(all_pairs, 45)

    def test_standings_use_points_then_time_then_id(self) -> None:
        table = standings(["01", "02", "03"], [
            GameScore("01", "02", 0.5, 0.5, 100, 101),
            GameScore("01", "03", 0.5, 0.5, 100, 100),
            GameScore("02", "03", 0.5, 0.5, 100, 100),
        ])
        self.assertEqual([row.student_id for row in table], ["01", "03", "02"])
