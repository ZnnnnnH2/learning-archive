"""Tests for the UI-independent cube timeline controller."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cube_model import CubeState, build_timeline  # noqa: E402
from replay import ReplaySession  # noqa: E402


class ReplaySessionTests(unittest.TestCase):
    def test_precomputes_states_and_supports_navigation(self) -> None:
        initial = CubeState.solved()
        actions = ("0+", "6-", "8+")
        session = ReplaySession(initial, actions)

        self.assertEqual(session.states, build_timeline(initial, actions))
        self.assertEqual(session.current_state, initial)
        self.assertEqual(session.total_steps, 3)
        self.assertEqual(session.completion, 0.0)
        self.assertFalse(session.completed)
        self.assertIsNone(session.current_action)
        self.assertEqual(session.next_action, "0+")

        session.play()
        self.assertTrue(session.playing)
        self.assertEqual(session.next(), session.states[1])
        self.assertTrue(session.playing)
        self.assertEqual(session.current_action, "0+")
        self.assertEqual(session.next_action, "6-")

        self.assertEqual(session.previous(), initial)
        self.assertFalse(session.playing)
        self.assertEqual(session.seek(2), session.states[2])
        self.assertEqual(session.completion, 2 / 3)

        session.play()
        self.assertEqual(session.next(), session.states[-1])
        self.assertTrue(session.completed)
        self.assertFalse(session.playing)
        self.assertEqual(session.completion, 1.0)
        self.assertIsNone(session.next_action)

    def test_empty_timeline_is_already_complete(self) -> None:
        session = ReplaySession(CubeState.solved(), ())

        self.assertTrue(session.completed)
        self.assertEqual(session.completion, 1.0)
        self.assertFalse(session.playing)
        self.assertEqual(session.play(), session.current_state)
        self.assertFalse(session.playing)

    def test_seek_rejects_out_of_range_or_non_integer_positions(self) -> None:
        session = ReplaySession(CubeState.solved(), ("0+",))

        for value in (-1, 2):
            with self.subTest(value=value):
                with self.assertRaises(IndexError):
                    session.seek(value)
        for value in (True, 1.0, "1"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    session.seek(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
