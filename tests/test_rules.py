import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gobang_gui import (  # noqa: E402
    BLACK,
    EMPTY,
    RULE_FREESTYLE,
    RULE_RENJU_CLASSROOM,
    WHITE,
    GomokuState,
    Move,
)


class RenjuRuleTests(unittest.TestCase):
    def classroom_state(self) -> GomokuState:
        state = GomokuState(ruleset=RULE_RENJU_CLASSROOM)
        # 绕过首手限制，以便直接构造中局禁手图形。
        state.history.append(Move(0, 0, WHITE))
        state.side_to_move = BLACK
        return state

    @staticmethod
    def put(state: GomokuState, color: int, *points: tuple[int, int]) -> None:
        for row, col in points:
            state.board[row][col] = color

    def test_classroom_opening_requires_black_center(self) -> None:
        state = GomokuState(ruleset=RULE_RENJU_CLASSROOM)
        verdict = state.analyze_move(0, 0)
        self.assertFalse(verdict.legal)
        self.assertEqual(verdict.forbidden, "opening")
        self.assertTrue(state.analyze_move(7, 7).legal)

    def test_black_exact_five_wins(self) -> None:
        state = self.classroom_state()
        self.put(state, BLACK, (7, 3), (7, 4), (7, 5), (7, 6))
        verdict = state.analyze_move(7, 7)
        self.assertTrue(verdict.legal)
        self.assertEqual(verdict.winner, BLACK)
        state.play(7, 7)
        self.assertEqual(state.winner, BLACK)

    def test_black_exact_five_has_priority_over_simultaneous_fours(self) -> None:
        state = self.classroom_state()
        self.put(
            state,
            BLACK,
            (7, 3),
            (7, 4),
            (7, 5),
            (7, 6),
            (4, 7),
            (5, 7),
            (6, 7),
            (4, 4),
            (5, 5),
            (6, 6),
        )
        verdict = state.analyze_move(7, 7)
        self.assertTrue(verdict.legal)
        self.assertEqual(verdict.winner, BLACK)

    def test_black_overline_is_forbidden_but_white_overline_wins(self) -> None:
        black_state = self.classroom_state()
        self.put(black_state, BLACK, (7, 3), (7, 4), (7, 5), (7, 6), (7, 7))
        verdict = black_state.analyze_move(7, 8)
        self.assertFalse(verdict.legal)
        self.assertEqual(verdict.forbidden, "overline")

        white_state = self.classroom_state()
        self.put(white_state, WHITE, (7, 3), (7, 4), (7, 5), (7, 6), (7, 7))
        white_state.side_to_move = WHITE
        verdict = white_state.analyze_move(7, 8)
        self.assertTrue(verdict.legal)
        self.assertEqual(verdict.winner, WHITE)

    def test_black_double_four_is_forbidden(self) -> None:
        state = self.classroom_state()
        self.put(
            state,
            BLACK,
            (7, 5),
            (7, 6),
            (7, 8),
            (5, 7),
            (6, 7),
            (8, 7),
        )
        verdict = state.analyze_move(7, 7)
        self.assertFalse(verdict.legal)
        self.assertEqual(verdict.forbidden, "double_four")

    def test_black_double_open_three_is_forbidden(self) -> None:
        state = self.classroom_state()
        self.put(state, BLACK, (7, 6), (7, 8), (6, 7), (8, 7))
        verdict = state.analyze_move(7, 7)
        self.assertFalse(verdict.legal)
        self.assertEqual(verdict.forbidden, "double_three")

    def test_edge_pattern_is_not_a_second_open_three(self) -> None:
        state = self.classroom_state()
        self.put(state, BLACK, (0, 6), (0, 8), (1, 7), (2, 7))
        verdict = state.analyze_move(0, 7)
        self.assertTrue(verdict.legal)
        self.assertEqual(verdict.winner, EMPTY)

    def test_freestyle_has_no_forbidden_move(self) -> None:
        state = GomokuState(ruleset=RULE_FREESTYLE)
        self.put(state, BLACK, (7, 3), (7, 4), (7, 5), (7, 6), (7, 7))
        verdict = state.analyze_move(7, 8)
        self.assertTrue(verdict.legal)
        self.assertEqual(verdict.winner, BLACK)


if __name__ == "__main__":
    unittest.main()
