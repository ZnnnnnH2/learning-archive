"""Course-defined 3×3×3 cube state, input format, and move semantics.

This module deliberately has no Qt/OpenGL dependency.  It is the single
source of truth for the visualizer's state transitions, so the animation layer
can use :func:`describe_move` while the discrete state uses
:func:`apply_move`.

The coordinate convention is a direct port of ``course_core/problems.cpp``:
faces are ordered ``left, front, right, up, down, back`` and a sticker has a
position plus outward normal in ``{-1, 0, 1}³``.  In particular, move ``6``
is the front layer and move ``8`` is the back layer.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable, Sequence, TypeAlias


FACE_ORDER = ("left", "front", "right", "up", "down", "back")
"""Internal face order, identical to ``course_core::CubeFace``."""

INPUT_FACE_ORDER = ("back", "down", "front", "left", "right", "up")
"""Required order of the six named sections written to solver stdin."""

# The assignment's 2-D net is ``left / up / right`` with ``back`` above and
# ``front / down`` below.  A flat face matrix therefore is not always stored
# in the same row/column orientation as the course-core 3-D coordinate model.
# Values are clockwise quarter turns from the raw course text to ``FACE_ORDER``.
COURSE_INPUT_TURNS_CW = {
    "left": 3,
    "front": 0,
    "right": 1,
    "up": 0,
    "down": 0,
    "back": 2,
}

FACE_INDEX = {name: index for index, name in enumerate(FACE_ORDER)}
ACTION_TOKENS = tuple(f"{move}{suffix}" for move in range(9) for suffix in "+-")

FaceRef: TypeAlias = str | int
Vector3: TypeAlias = tuple[int, int, int]

_ACTION_PATTERN = re.compile(r"^[0-8][+-]$")
# Face order is left/front/right/up/down/back.  These are the fixed centre
# colors in the course's example input, so the default view uses the handout's
# y/r/g/p/w/b palette even before a user loads an initial state.
_DEFAULT_SOLVED_COLORS = ("g", "w", "b", "p", "r", "y")


@dataclass(frozen=True, slots=True)
class StickerLocation:
    """A sticker centre and its outward-facing normal in cube coordinates."""

    position: Vector3
    normal: Vector3


@dataclass(frozen=True, slots=True)
class MoveDescription:
    """The geometric interpretation of one course action token.

    ``sign`` is the right-hand quarter-turn sign around the positive global
    axis.  It is intentionally exposed for the OpenGL animation to use the
    same direction as the discrete move engine.
    """

    token: str
    axis: int
    layer: int
    sign: int
    axis_name: str
    layer_name: str
    label: str


@dataclass(frozen=True, slots=True)
class CubeState:
    """Immutable stickers in :data:`FACE_ORDER`, row-major within each face.

    Construction validates the 6×9 printable-ASCII shape.  The stricter
    course-input rule (exactly six colors with nine stickers each) is enforced
    by :func:`parse_course_input` and :func:`format_course_input`; allowing a
    structurally valid labelled state here also makes move mapping tests and
    diagnostics straightforward.
    """

    faces: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        try:
            normalized = tuple(tuple(face) for face in self.faces)
        except TypeError as exc:
            raise ValueError("cube faces must be an iterable of six faces") from exc
        if len(normalized) != len(FACE_ORDER):
            raise ValueError("cube must contain exactly six faces")
        for face_index, stickers in enumerate(normalized):
            if len(stickers) != 9:
                raise ValueError(f"{FACE_ORDER[face_index]} must contain exactly 9 stickers")
            for sticker_index, sticker in enumerate(stickers):
                _validate_sticker(sticker, f"{FACE_ORDER[face_index]}[{sticker_index}]")
        object.__setattr__(self, "faces", normalized)

    @classmethod
    def solved(cls, colors: Sequence[str] = _DEFAULT_SOLVED_COLORS) -> CubeState:
        """Build a monochromatic, six-color solved cube.

        ``colors`` follows :data:`FACE_ORDER`; by default it uses the standard
        course palette in the orientation fixed by the example's centre
        stickers.
        """

        colors = tuple(colors)
        if len(colors) != len(FACE_ORDER):
            raise ValueError("a solved cube requires exactly six face colors")
        if len(set(colors)) != len(colors):
            raise ValueError("a solved cube requires six distinct face colors")
        for index, color in enumerate(colors):
            _validate_sticker(color, f"colors[{index}]")
        return cls(tuple((color,) * 9 for color in colors))

    def face(self, face: FaceRef) -> tuple[str, ...]:
        """Return one immutable row-major face by name or internal index."""

        return self.faces[_face_index(face)]


def _validate_sticker(sticker: object, name: str) -> None:
    if not isinstance(sticker, str) or len(sticker) != 1:
        raise ValueError(f"{name} must be one printable non-space ASCII sticker")
    codepoint = ord(sticker)
    if codepoint < 0x21 or codepoint > 0x7E:
        raise ValueError(f"{name} must be one printable non-space ASCII sticker")


def _face_index(face: FaceRef) -> int:
    if isinstance(face, int) and not isinstance(face, bool):
        if 0 <= face < len(FACE_ORDER):
            return face
        raise ValueError(f"cube face index must be 0 through {len(FACE_ORDER) - 1}")
    if isinstance(face, str) and face in FACE_INDEX:
        return FACE_INDEX[face]
    raise ValueError(f"cube face must be one of: {', '.join(FACE_ORDER)}")


def _require_state(state: CubeState) -> CubeState:
    if not isinstance(state, CubeState):
        raise TypeError("state must be a CubeState")
    return state


def validate_course_state(state: CubeState) -> None:
    """Validate the six-colors/nine-stickers course invariant.

    The move engine preserves this invariant for states returned by the parser.
    A separate validator keeps ``CubeState`` useful for labelled mapping tests
    without allowing invalid raw solver input to pass through the UI.
    """

    state = _require_state(state)
    counts = Counter(sticker for face in state.faces for sticker in face)
    if len(counts) != 6:
        raise ValueError("cube input must use exactly six unique sticker colors")
    bad_counts = [(sticker, count) for sticker, count in sorted(counts.items()) if count != 9]
    if bad_counts:
        detail = ", ".join(f"{sticker!r}: {count}" for sticker, count in bad_counts)
        raise ValueError(f"each cube sticker color must occur exactly 9 times ({detail})")


def _turn_face_clockwise(stickers: Sequence[str], turns: int) -> tuple[str, ...]:
    """Rotate one 3×3 face clockwise without changing its sticker values."""

    grid = [list(stickers[row * 3 : row * 3 + 3]) for row in range(3)]
    for _ in range(turns % 4):
        grid = [[grid[2 - col][row] for col in range(3)] for row in range(3)]
    return tuple(sticker for row in grid for sticker in row)


def parse_course_input(text: str) -> CubeState:
    """Parse the fixed six-section raw text input sent to a student solver.

    The six headers must appear in :data:`INPUT_FACE_ORDER`; every header is
    followed by exactly three non-empty rows of three whitespace-separated
    one-character stickers.  Blank separator lines are allowed.
    """

    if not isinstance(text, str):
        raise TypeError("course input must be text")

    nonempty_lines = [(number, line.strip()) for number, line in enumerate(text.splitlines(), start=1) if line.strip()]
    line_index = 0
    parsed_faces: dict[str, tuple[str, ...]] = {}

    for expected_face in INPUT_FACE_ORDER:
        if line_index >= len(nonempty_lines):
            raise ValueError(f"missing required '{expected_face}:' section")
        header_line_number, header = nonempty_lines[line_index]
        header_match = re.fullmatch(r"([a-z]+):", header)
        if header_match is None:
            raise ValueError(f"line {header_line_number}: expected '{expected_face}:' section header")
        actual_face = header_match.group(1)
        if actual_face != expected_face:
            raise ValueError(
                f"line {header_line_number}: expected '{expected_face}:', found '{actual_face}:'"
            )
        line_index += 1

        stickers: list[str] = []
        for row in range(3):
            if line_index >= len(nonempty_lines):
                raise ValueError(f"{expected_face}: missing row {row + 1} of 3")
            row_line_number, row_text = nonempty_lines[line_index]
            tokens = row_text.split()
            if len(tokens) != 3:
                raise ValueError(
                    f"line {row_line_number}: {expected_face} row {row + 1} must contain 3 whitespace-separated stickers"
                )
            for col, sticker in enumerate(tokens):
                _validate_sticker(sticker, f"line {row_line_number} ({expected_face}[{row},{col}])")
            stickers.extend(tokens)
            line_index += 1
        parsed_faces[expected_face] = _turn_face_clockwise(
            stickers, COURSE_INPUT_TURNS_CW[expected_face]
        )

    if line_index != len(nonempty_lines):
        line_number, extra = nonempty_lines[line_index]
        raise ValueError(f"line {line_number}: unexpected content after 'up:' section: {extra!r}")

    state = CubeState(tuple(parsed_faces[face] for face in FACE_ORDER))
    validate_course_state(state)
    return state


def format_course_input(state: CubeState) -> str:
    """Return canonical raw solver input in :data:`INPUT_FACE_ORDER`."""

    state = _require_state(state)
    validate_course_state(state)
    sections: list[str] = []
    for face_name in INPUT_FACE_ORDER:
        stickers = _turn_face_clockwise(
            state.face(face_name), -COURSE_INPUT_TURNS_CW[face_name]
        )
        rows = [" ".join(stickers[row * 3 : row * 3 + 3]) for row in range(3)]
        sections.append("\n".join((f"{face_name}:", *rows)))
    return "\n\n".join(sections) + "\n"


def describe_move(token: str) -> MoveDescription:
    """Validate and describe one ``0+`` through ``8-`` course action."""

    if not isinstance(token, str) or _ACTION_PATTERN.fullmatch(token) is None:
        raise ValueError("cube action must be a token in the form '0+' through '8-'")

    move = ord(token[0]) - ord("0")
    axis = move // 3
    offset = move % 3
    # The first two groups increase in global coordinate order; the final
    # group is explicitly front→back, therefore 6 is z=+1 and 8 is z=-1.
    layer = 1 - offset if axis == 2 else offset - 1
    plus_sign = 1 if axis == 0 else -1
    sign = plus_sign if token[1] == "+" else -plus_sign

    axis_names = ("左右", "上下", "前后")
    layer_names = (
        ("左层", "中层", "右层"),
        ("下层", "中层", "上层"),
        ("前层", "中层", "后层"),
    )
    layer_name = layer_names[axis][offset]
    if offset == 1:
        label = f"{layer_name}沿{axis_names[axis]}轴{'正向' if sign > 0 else '反向'}旋转"
    else:
        # These six phrases follow the handout convention documented beside
        # ``parseCubeMove`` in course_core.
        clockwise_for_plus = move in {0, 5, 6}
        clockwise = clockwise_for_plus if token[1] == "+" else not clockwise_for_plus
        label = f"{layer_name}{'顺时针' if clockwise else '逆时针'}"
    return MoveDescription(token, axis, layer, sign, axis_names[axis], layer_name, label)


def parse_action_output(stdout: str) -> tuple[str, ...]:
    """Parse a solver's complete stdout as an action-token stream.

    Empty output is syntactically valid; callers decide whether it solves their
    initial state.  A non-empty stream must end in a newline.  Every
    non-whitespace item must be a standalone course action, so status lines
    and debug output are rejected rather than ignored.
    """

    if not isinstance(stdout, str):
        raise TypeError("solver stdout must be text")
    tokens = tuple(stdout.split())
    for index, token in enumerate(tokens):
        try:
            describe_move(token)
        except ValueError as exc:
            raise ValueError(f"stdout token {index + 1} ({token!r}) is invalid: {exc}") from exc
    if tokens and not stdout.endswith("\n"):
        raise ValueError("stdout 动作序列必须以换行结束")
    return tokens


def sticker_location(face: FaceRef, row: int, col: int) -> StickerLocation:
    """Return the course-core geometric location of a sticker."""

    face_index = _face_index(face)
    if not isinstance(row, int) or isinstance(row, bool) or not 0 <= row < 3:
        raise ValueError("sticker row must be 0, 1, or 2")
    if not isinstance(col, int) or isinstance(col, bool) or not 0 <= col < 3:
        raise ValueError("sticker column must be 0, 1, or 2")

    if face_index == 0:  # left
        return StickerLocation((-1, 1 - row, col - 1), (-1, 0, 0))
    if face_index == 1:  # front
        return StickerLocation((col - 1, 1 - row, 1), (0, 0, 1))
    if face_index == 2:  # right
        return StickerLocation((1, 1 - row, 1 - col), (1, 0, 0))
    if face_index == 3:  # up
        return StickerLocation((col - 1, 1, row - 1), (0, 1, 0))
    if face_index == 4:  # down
        return StickerLocation((col - 1, -1, 1 - row), (0, -1, 0))
    return StickerLocation((1 - col, 1 - row, -1), (0, 0, -1))  # back


def _face_coordinates(location: StickerLocation) -> tuple[int, int, int]:
    """Inverse of :func:`sticker_location`, ported from course_core."""

    x, y, z = location.position
    nx, ny, nz = location.normal
    if (nx, ny, nz) == (-1, 0, 0):
        face, row, col = 0, 1 - y, z + 1
    elif (nx, ny, nz) == (0, 0, 1):
        face, row, col = 1, 1 - y, x + 1
    elif (nx, ny, nz) == (1, 0, 0):
        face, row, col = 2, 1 - y, 1 - z
    elif (nx, ny, nz) == (0, 1, 0):
        face, row, col = 3, z + 1, x + 1
    elif (nx, ny, nz) == (0, -1, 0):
        face, row, col = 4, 1 - z, x + 1
    elif (nx, ny, nz) == (0, 0, -1):
        face, row, col = 5, 1 - y, 1 - x
    else:
        raise RuntimeError("internal cube coordinate mapping failure")
    if not 0 <= row < 3 or not 0 <= col < 3:
        raise RuntimeError("internal cube coordinate mapping failure")
    return face, row, col


def _rotate_quarter(value: Vector3, axis: int, sign: int) -> Vector3:
    """Rotate a vector by one signed right-hand quarter turn."""

    x, y, z = value
    if axis == 0:
        return (x, -z, y) if sign > 0 else (x, z, -y)
    if axis == 1:
        return (z, y, -x) if sign > 0 else (-z, y, x)
    if axis == 2:
        return (-y, x, z) if sign > 0 else (y, -x, z)
    raise RuntimeError("internal cube axis mapping failure")


def apply_move(state: CubeState, token: str) -> CubeState:
    """Return a new state after exactly one course-defined quarter turn."""

    state = _require_state(state)
    move = describe_move(token)
    next_faces: list[list[str | None]] = [[None] * 9 for _ in FACE_ORDER]
    assigned = [False] * 54

    for source_face in range(len(FACE_ORDER)):
        for row in range(3):
            for col in range(3):
                location = sticker_location(source_face, row, col)
                if location.position[move.axis] == move.layer:
                    location = StickerLocation(
                        _rotate_quarter(location.position, move.axis, move.sign),
                        _rotate_quarter(location.normal, move.axis, move.sign),
                    )
                destination_face, destination_row, destination_col = _face_coordinates(location)
                destination_index = destination_face * 9 + destination_row * 3 + destination_col
                if assigned[destination_index]:
                    raise RuntimeError("internal cube move mapping collision")
                assigned[destination_index] = True
                next_faces[destination_face][destination_row * 3 + destination_col] = state.faces[source_face][row * 3 + col]

    if not all(assigned) or any(sticker is None for face in next_faces for sticker in face):
        raise RuntimeError("internal cube move mapping gap")
    return CubeState(tuple(tuple(sticker for sticker in face if sticker is not None) for face in next_faces))


def is_goal(state: CubeState) -> bool:
    """Whether all six faces are monochromatic and use distinct colors."""

    state = _require_state(state)
    colors: list[str] = []
    for face in state.faces:
        if any(sticker != face[0] for sticker in face):
            return False
        colors.append(face[0])
    return len(set(colors)) == len(FACE_ORDER)


def build_timeline(initial: CubeState, actions: Iterable[str]) -> tuple[CubeState, ...]:
    """Precompute initial state plus one state after each action in order."""

    initial = _require_state(initial)
    if isinstance(actions, (str, bytes)):
        raise TypeError("actions must be an iterable of action tokens, not one string")
    try:
        iterator = iter(actions)
    except TypeError as exc:
        raise TypeError("actions must be an iterable of action tokens") from exc

    timeline = [initial]
    for index, token in enumerate(iterator):
        try:
            timeline.append(apply_move(timeline[-1], token))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"actions[{index}] is invalid: {exc}") from exc
    return tuple(timeline)


__all__ = [
    "ACTION_TOKENS",
    "FACE_INDEX",
    "FACE_ORDER",
    "INPUT_FACE_ORDER",
    "CubeState",
    "MoveDescription",
    "StickerLocation",
    "apply_move",
    "build_timeline",
    "describe_move",
    "format_course_input",
    "is_goal",
    "parse_action_output",
    "parse_course_input",
    "sticker_location",
    "validate_course_state",
]
