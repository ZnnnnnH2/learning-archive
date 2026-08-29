"""Headless checks for cube_view's renderer-only geometry helpers."""

from __future__ import annotations

import math
from pathlib import Path
import string
import sys
import unittest


VISUALIZER_DIR = Path(__file__).resolve().parents[1]
if str(VISUALIZER_DIR) not in sys.path:
    sys.path.insert(0, str(VISUALIZER_DIR))

from cube_model import CubeState, apply_move, describe_move, sticker_location  # noqa: E402
from cube_view import (  # noqa: E402
    FACE_ORDER,
    STICKER_LIFT,
    affected_sticker_indices,
    animated_sticker_geometry,
    rotate_point,
    scene_vertex_data,
    sticker_color,
    sticker_geometry,
    sticker_in_move_layer,
)


class CubeViewGeometryTests(unittest.TestCase):
    def assertVecClose(self, actual, expected, tolerance: float = 1e-7) -> None:
        self.assertEqual(len(actual), 3)
        self.assertEqual(len(expected), 3)
        for actual_component, expected_component in zip(actual, expected):
            self.assertTrue(math.isclose(actual_component, expected_component, abs_tol=tolerance))

    def test_geometry_contains_exactly_54_lifted_sticker_quads(self) -> None:
        geometry = sticker_geometry(CubeState.solved())

        self.assertEqual(len(geometry), 54)
        self.assertEqual([sticker.index for sticker in geometry], list(range(54)))
        self.assertEqual({sticker.face for sticker in geometry}, set(FACE_ORDER))
        for sticker in geometry:
            location = sticker_location(sticker.face, sticker.row, sticker.col)
            expected_center = tuple(
                location.position[axis] + STICKER_LIFT * location.normal[axis]
                for axis in range(3)
            )
            self.assertVecClose(sticker.center, expected_center)
            # Counter-clockwise corners must point along the face normal.
            first_edge = tuple(sticker.corners[1][axis] - sticker.corners[0][axis] for axis in range(3))
            second_edge = tuple(sticker.corners[2][axis] - sticker.corners[1][axis] for axis in range(3))
            cross = (
                first_edge[1] * second_edge[2] - first_edge[2] * second_edge[1],
                first_edge[2] * second_edge[0] - first_edge[0] * second_edge[2],
                first_edge[0] * second_edge[1] - first_edge[1] * second_edge[0],
            )
            self.assertGreater(sum(cross[axis] * sticker.normal[axis] for axis in range(3)), 0)

    def test_affected_layer_classification_matches_course_move_description(self) -> None:
        # Outer layers contain a full face plus four three-sticker strips;
        # middle slices contain the four middle strips only.
        for token in ("0+", "2-", "3+", "5-", "6+", "8-"):
            self.assertEqual(len(affected_sticker_indices(token)), 21)
        for token in ("1+", "4-", "7+"):
            self.assertEqual(len(affected_sticker_indices(token)), 12)

        for token in (f"{move}{sign}" for move in range(9) for sign in "+-"):
            description = describe_move(token)
            affected = set(affected_sticker_indices(token))
            for face_index, face in enumerate(FACE_ORDER):
                for row in range(3):
                    for col in range(3):
                        index = face_index * 9 + row * 3 + col
                        expected = sticker_location(face, row, col).position[description.axis] == description.layer
                        self.assertIs(sticker_in_move_layer(face, row, col, token), expected)
                        self.assertIs(index in affected, expected)

    def test_animation_rotates_only_affected_quads_and_never_changes_state(self) -> None:
        state = CubeState.solved()
        original = {sticker.index: sticker for sticker in sticker_geometry(state)}
        halfway = {sticker.index: sticker for sticker in animated_sticker_geometry(state, "0+", 0.5)}
        affected = set(affected_sticker_indices("0+"))
        description = describe_move("0+")

        for index, sticker in original.items():
            if index not in affected:
                self.assertEqual(halfway[index], sticker)
                continue
            self.assertVecClose(
                halfway[index].center,
                rotate_point(sticker.center, description.axis, description.sign * math.pi / 4),
            )
            for actual_corner, expected_corner in zip(halfway[index].corners, sticker.corners):
                self.assertVecClose(
                    actual_corner,
                    rotate_point(expected_corner, description.axis, description.sign * math.pi / 4),
                )

        self.assertEqual(state, CubeState.solved())

    def test_all_animation_endpoints_match_the_discrete_course_move_state(self) -> None:
        labels = string.ascii_uppercase + string.ascii_lowercase + "01"
        state = CubeState(tuple(tuple(labels[face * 9 : face * 9 + 9]) for face in range(6)))

        def location_key(sticker):
            return tuple(round(value, 6) for value in (*sticker.center, *sticker.normal))

        for token in (f"{move}{sign}" for move in range(9) for sign in "+-"):
            with self.subTest(token=token):
                animated = {
                    location_key(sticker): sticker.sticker
                    for sticker in animated_sticker_geometry(state, token, 1.0)
                }
                discrete = {
                    location_key(sticker): sticker.sticker
                    for sticker in sticker_geometry(apply_move(state, token))
                }
                self.assertEqual(animated, discrete)

    def test_scene_payload_has_one_body_and_54_sticker_quads(self) -> None:
        payload, vertex_count = scene_vertex_data(CubeState.solved(), "8-", 0.25)

        # Six cube-body quads plus one quad per sticker; each becomes two triangles.
        self.assertEqual(vertex_count, (6 + 54) * 6)
        self.assertEqual(len(payload), vertex_count * 6 * 4)

    def test_standard_and_arbitrary_color_labels_remain_distinguishable(self) -> None:
        self.assertNotEqual(sticker_color("y"), sticker_color("r"))
        self.assertNotEqual(sticker_color("A"), sticker_color("a"))
        self.assertNotEqual(sticker_color("Y"), sticker_color("y"))
