"""Logic tests for the standalone Python cube domain model."""

from __future__ import annotations

import string
import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cube_model import (  # noqa: E402
    FACE_ORDER,
    INPUT_FACE_ORDER,
    CubeState,
    StickerLocation,
    apply_move,
    build_timeline,
    describe_move,
    format_course_input,
    is_goal,
    parse_action_output,
    parse_course_input,
    sticker_location,
)


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


def labelled_state() -> CubeState:
    """A structurally valid state with a different printable character per sticker."""

    labels = string.ascii_uppercase + string.ascii_lowercase + "01"
    assert len(labels) == 54
    return CubeState(tuple(tuple(labels[face * 9 : face * 9 + 9]) for face in range(6)))


# Flat left/front/right/up/down/back output for the uniquely-labelled state
# above.  These 18 complete 54-sticker permutations were recorded from the
# course_core coordinate mapping, rather than being derived by the test from
# the implementation under test.  They make a face-orientation regression
# immediately visible even when inverse/four-turn properties still hold.
COURSE_CORE_GOLDEN_PERMUTATIONS = {
    "0+": "GDAHEBIFCbKLeNOhQRSTUVWXYZa1cdyfgvijJlmMopPrstuqwxnz0k",
    "0-": "CFIBEHADGkKLnNOqQRSTUVWXYZaJcdMfgPij1lmyopvrstuhwxez0b",
    "1+": "ABCDEFGHIJcLMfOPiRSTUVWXYZab0dexghujkKmnNpqQstrvwoyzl1",
    "1-": "ABCDEFGHIJlLMoOPrRSTUVWXYZabKdeNghQjk0mnxpqustivwfyzc1",
    "2+": "ABCDEFGHIJKdMNgPQjUXaTWZSVYbczefwhitklLnoOqrRsuvpxym01",
    "2-": "ABCDEFGHIJKmMNpPQsYVSZWTaXUbcLefOhiRklznowqrtjuvgxyd01",
    "3+": "ABCDEFPQRJKLMNOYZaSTUVWXz01bcdefghijmpslorknqtuvwxyGHI",
    "3-": "ABCDEFz01JKLMNOGHISTUVWXPQRbcdefghijqnkrolspmtuvwxyYZa",
    "4+": "ABCMNOGHIJKLVWXPQRSTUwxyYZabcdefghijklmnopqrstuvDEFz01",
    "4-": "ABCwxyGHIJKLDEFPQRSTUMNOYZabcdefghijklmnopqrstuvVWXz01",
    "5+": "JKLDEFGHISTUMNOPQRtuvVWXYZahebifcjgdklmnopqrsABCwxyz01",
    "5-": "tuvDEFGHIABCMNOPQRJKLVWXYZadgjcfibehklmnopqrsSTUwxyz01",
    "6+": "ABkDElGHmPMJQNKROLhTUiWXjZabcdefgIFCYVSnopqrstuvwxyz01",
    "6-": "ABjDEiGHhLORKNQJMPmTUlWXkZabcdefgSVYCFInopqrstuvwxyz01",
    "7+": "AnCDoFGpIJKLMNOPQRSeUVfXYgabcdHEBhijklmZWTqrstuvwxyz01",
    "7-": "AgCDfFGeIJKLMNOPQRSpUVoXYnabcdTWZhijklmBEHqrstuvwxyz01",
    "8+": "qBCrEFsHIJKLMNOPQRSTbVWcYZdGDAefghijklmnopaXUvy1ux0twz",
    "8-": "dBCcEFbHIJKLMNOPQRSTsVWrYZqUXaefghijklmnopADGzwt0xu1yv",
}


def locate(state: CubeState, label: str) -> tuple[str, int, int]:
    for face_index, face in enumerate(state.faces):
        for index, sticker in enumerate(face):
            if sticker == label:
                return FACE_ORDER[face_index], index // 3, index % 3
    raise AssertionError(f"missing label {label!r}")


class CourseInputTests(unittest.TestCase):
    def test_parse_sample_and_canonical_round_trip(self) -> None:
        state = parse_course_input(SAMPLE_INPUT)
        self.assertEqual(state.face("back")[:3], ("y", "b", "y"))
        self.assertEqual(state.face("down")[3:6], ("w", "r", "w"))

        formatted = format_course_input(state)
        headers = [line for line in formatted.splitlines() if line.endswith(":")]
        self.assertEqual(headers, [f"{name}:" for name in INPUT_FACE_ORDER])
        self.assertEqual(formatted, SAMPLE_INPUT)
        self.assertEqual(parse_course_input(formatted), state)

    def test_assignment_sample_is_solved_by_its_published_action_sequence(self) -> None:
        state = parse_course_input(SAMPLE_INPUT)
        for action in ("3-", "6+", "4-", "7+", "1-"):
            state = apply_move(state, action)
        self.assertTrue(is_goal(state))

    def test_rejects_wrong_section_shape_order_and_stickers(self) -> None:
        wrong_order = SAMPLE_INPUT.replace("back:", "front:", 1)
        with self.assertRaisesRegex(ValueError, "expected 'back:'"):
            parse_course_input(wrong_order)

        bad_row = SAMPLE_INPUT.replace("g g r", "g g", 1)
        with self.assertRaisesRegex(ValueError, "must contain 3"):
            parse_course_input(bad_row)

        non_ascii = SAMPLE_INPUT.replace("g g r", "é g r", 1)
        with self.assertRaisesRegex(ValueError, "printable non-space ASCII"):
            parse_course_input(non_ascii)

        bad_counts = SAMPLE_INPUT.replace("g g r", "r g r", 1)
        with self.assertRaisesRegex(ValueError, "exactly 9"):
            parse_course_input(bad_counts)

        with self.assertRaisesRegex(ValueError, "unexpected content"):
            parse_course_input(SAMPLE_INPUT + "\nextra:\n")


class MoveOutputTests(unittest.TestCase):
    def test_parse_action_output_is_a_strict_token_stream(self) -> None:
        self.assertEqual(parse_action_output(" 0+\n6-  8+\n"), ("0+", "6-", "8+"))
        self.assertEqual(parse_action_output("\n\t "), ())

        for output in ("0+ debug", "9+", "0+1-", "0+ # detail"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "invalid"):
                parse_action_output(output)
        with self.assertRaisesRegex(ValueError, "换行"):
            parse_action_output("0+")

    def test_front_back_move_description_is_course_ordered(self) -> None:
        front_plus = describe_move("6+")
        back_plus = describe_move("8+")
        self.assertEqual((front_plus.axis, front_plus.layer, front_plus.sign), (2, 1, -1))
        self.assertEqual((back_plus.axis, back_plus.layer, back_plus.sign), (2, -1, -1))
        self.assertEqual(describe_move("8-").sign, 1)


class CubeMoveTests(unittest.TestCase):
    def test_all_18_actions_match_full_course_core_golden_permutations(self) -> None:
        state = labelled_state()
        self.assertEqual(set(COURSE_CORE_GOLDEN_PERMUTATIONS), {f"{move}{sign}" for move in range(9) for sign in "+-"})
        for token, expected_flat_state in COURSE_CORE_GOLDEN_PERMUTATIONS.items():
            with self.subTest(token=token):
                self.assertEqual(len(expected_flat_state), 54)
                actual_flat_state = "".join(
                    sticker for face in apply_move(state, token).faces for sticker in face
                )
                self.assertEqual(actual_flat_state, expected_flat_state)

    def test_every_action_has_inverse_and_order_four(self) -> None:
        solved = CubeState.solved()
        for move in range(9):
            with self.subTest(move=move):
                plus, minus = f"{move}+", f"{move}-"
                self.assertEqual(apply_move(apply_move(solved, plus), minus), solved)
                after_four = solved
                for _ in range(4):
                    after_four = apply_move(after_four, plus)
                self.assertEqual(after_four, solved)

    def test_sticker_locations_are_unique_and_match_course_coordinates(self) -> None:
        locations = [
            sticker_location(face, row, col)
            for face in FACE_ORDER
            for row in range(3)
            for col in range(3)
        ]
        self.assertEqual(len(locations), 54)
        self.assertEqual(len({(location.position, location.normal) for location in locations}), 54)
        self.assertEqual(
            sticker_location("left", 0, 0), StickerLocation((-1, 1, -1), (-1, 0, 0))
        )
        self.assertEqual(
            sticker_location("back", 2, 2), StickerLocation((-1, -1, -1), (0, 0, -1))
        )

    def test_outer_face_gold_directions(self) -> None:
        state = labelled_state()
        expected_destinations = {
            "0+": ("left", 0, 0, "left", 0, 2),
            "2+": ("right", 0, 0, "right", 2, 0),
            "3+": ("down", 0, 0, "down", 2, 0),
            "5+": ("up", 0, 0, "up", 0, 2),
            "6+": ("front", 0, 0, "front", 0, 2),
            "8+": ("back", 0, 0, "back", 2, 0),
        }
        for action, (source_face, source_row, source_col, dest_face, dest_row, dest_col) in expected_destinations.items():
            with self.subTest(action=action):
                label = state.face(source_face)[source_row * 3 + source_col]
                self.assertEqual(locate(apply_move(state, action), label), (dest_face, dest_row, dest_col))

    def test_goal_and_timeline(self) -> None:
        solved = CubeState.solved()
        self.assertTrue(is_goal(solved))
        moved = apply_move(solved, "0+")
        self.assertFalse(is_goal(moved))

        actions = ("0+", "4-", "8+")
        timeline = build_timeline(solved, actions)
        self.assertEqual(len(timeline), len(actions) + 1)
        self.assertEqual(timeline[0], solved)
        self.assertEqual(timeline[-1], apply_move(apply_move(apply_move(solved, "0+"), "4-"), "8+"))
        with self.assertRaisesRegex(ValueError, "actions\\[1\\]"):
            build_timeline(solved, ("0+", "oops"))


if __name__ == "__main__":
    unittest.main()
