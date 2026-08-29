"""PySide6/OpenGL rendering for the course's three-by-three cube.

The rule model deliberately remains in :mod:`cube_model`.  This module only
turns the model's sticker locations into drawable quads.  Its geometry helpers
do not require a Qt application or an OpenGL context, so the coordinate and
animation mapping can be tested on CI/headless machines.

``CubeView.set_animation(state, token, progress)`` is intentionally a visual
operation: it keeps ``state`` unchanged and rotates just the affected sticker
quads by ``progress * 90`` degrees.  The controller commits the next
``CubeState`` only after its animation finishes.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, replace
import math
from typing import Iterable, Sequence

try:  # Supports both ``python app.py`` and ``python -m cube.visualizer.app``.
    from .cube_model import CubeState, describe_move, sticker_location
except ImportError:  # pragma: no cover - exercised by the standalone launcher.
    from cube_model import CubeState, describe_move, sticker_location


# ``cube_model`` follows the handout and course_core face order.  Keeping the
# order local makes this module usable as a plain script as well as a package.
FACE_ORDER: tuple[str, ...] = ("left", "front", "right", "up", "down", "back")

# World-space dimensions.  The model's integer coordinates describe cubie
# centres (-1, 0, 1); stickers sit a little above the corresponding cubie face.
CUBIE_HALF_SIZE = 0.46
STICKER_LIFT = 0.485
STICKER_HALF_SIZE = 0.405

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class StickerGeometry:
    """A single sticker's immutable world-space quad.

    ``index`` is the row-major ``face * 9 + row * 3 + column`` index used by
    ``CubeState.faces``.  ``corners`` are counter-clockwise when viewed from
    outside the cube, making them suitable for the OpenGL triangle order.
    """

    index: int
    face: str
    row: int
    col: int
    sticker: str
    center: Vec3
    normal: Vec3
    corners: tuple[Vec3, Vec3, Vec3, Vec3]


def _as_vec3(value: Sequence[float]) -> Vec3:
    """Convert cube-model coordinates to a small, renderer-friendly tuple."""

    if len(value) != 3:
        raise ValueError("a cube coordinate must have exactly three components")
    return float(value[0]), float(value[1]), float(value[2])


def _add(left: Vec3, right: Vec3) -> Vec3:
    return left[0] + right[0], left[1] + right[1], left[2] + right[2]


def _subtract(left: Vec3, right: Vec3) -> Vec3:
    return left[0] - right[0], left[1] - right[1], left[2] - right[2]


def _scale(value: Vec3, scalar: float) -> Vec3:
    return value[0] * scalar, value[1] * scalar, value[2] * scalar


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(value: Vec3) -> float:
    return math.sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])


def _normalise(value: Vec3) -> Vec3:
    magnitude = _length(value)
    if magnitude == 0:
        raise ValueError("cannot normalise a zero-length vector")
    return _scale(value, 1.0 / magnitude)


def _sticker_basis(normal: Vec3) -> tuple[Vec3, Vec3]:
    """Return a right-handed in-plane basis for a sticker normal."""

    # Avoid a parallel reference vector on the up/down faces.
    reference = (1.0, 0.0, 0.0) if abs(normal[1]) > 0.9 else (0.0, 1.0, 0.0)
    horizontal = _normalise(_cross(reference, normal))
    vertical = _normalise(_cross(normal, horizontal))
    return horizontal, vertical


def sticker_index(face: str | int, row: int, col: int) -> int:
    """Return the stable 0..53 flat sticker index for a handout coordinate."""

    face_index = int(face) if isinstance(face, int) else FACE_ORDER.index(face)
    if not 0 <= face_index < len(FACE_ORDER) or not 0 <= row < 3 or not 0 <= col < 3:
        raise ValueError("cube sticker coordinates must be a face and row/column in 0..2")
    return face_index * 9 + row * 3 + col


def _move_parts(token_or_description: str | object) -> tuple[int, int, int]:
    """Normalise a course ``MoveDescription`` or token to ``axis/layer/sign``."""

    description = describe_move(token_or_description) if isinstance(token_or_description, str) else token_or_description
    try:
        axis = int(description.axis)  # type: ignore[attr-defined]
        layer = int(description.layer)  # type: ignore[attr-defined]
        sign = int(description.sign)  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - protects future API misuse.
        raise TypeError("move descriptions must expose axis, layer, and sign") from exc
    if axis not in (0, 1, 2) or layer not in (-1, 0, 1) or sign not in (-1, 1):
        raise ValueError("invalid cube move description")
    return axis, layer, sign


def sticker_in_move_layer(face: str | int, row: int, col: int, token_or_description: str | object) -> bool:
    """Whether this sticker belongs to the slice turned by ``token``.

    The test deliberately uses the model's *cubie centre* rather than the
    lifted visual sticker position.  That gives outer turns 21 stickers and
    middle-slice turns 12, matching the course move engine exactly.
    """

    axis, layer, _ = _move_parts(token_or_description)
    location = sticker_location(face, row, col)
    return int(location.position[axis]) == layer


def affected_sticker_indices(token_or_description: str | object) -> tuple[int, ...]:
    """Return the stable indices whose sticker quads animate for a move."""

    return tuple(
        sticker_index(face, row, col)
        for face in FACE_ORDER
        for row in range(3)
        for col in range(3)
        if sticker_in_move_layer(face, row, col, token_or_description)
    )


def rotate_point(point: Vec3, axis: int, radians: float) -> Vec3:
    """Rotate a point around a positive global axis using right-hand rule."""

    cosine = math.cos(radians)
    sine = math.sin(radians)
    x, y, z = point
    if axis == 0:
        return x, y * cosine - z * sine, y * sine + z * cosine
    if axis == 1:
        return x * cosine + z * sine, y, -x * sine + z * cosine
    if axis == 2:
        return x * cosine - y * sine, x * sine + y * cosine, z
    raise ValueError("axis must be 0 (x), 1 (y), or 2 (z)")


def sticker_geometry(state: CubeState) -> tuple[StickerGeometry, ...]:
    """Build all 54 visible sticker quads for ``state`` without Qt/OpenGL."""

    output: list[StickerGeometry] = []
    for face_index, face in enumerate(FACE_ORDER):
        stickers = state.faces[face_index]
        if len(stickers) != 9:
            raise ValueError(f"{face} must contain exactly 9 stickers")
        for row in range(3):
            for col in range(3):
                location = sticker_location(face, row, col)
                position = _as_vec3(location.position)
                normal = _normalise(_as_vec3(location.normal))
                center = _add(position, _scale(normal, STICKER_LIFT))
                horizontal, vertical = _sticker_basis(normal)
                lower_left = _subtract(_subtract(center, _scale(horizontal, STICKER_HALF_SIZE)), _scale(vertical, STICKER_HALF_SIZE))
                lower_right = _add(_subtract(center, _scale(vertical, STICKER_HALF_SIZE)), _scale(horizontal, STICKER_HALF_SIZE))
                upper_right = _add(_add(center, _scale(horizontal, STICKER_HALF_SIZE)), _scale(vertical, STICKER_HALF_SIZE))
                upper_left = _add(_subtract(center, _scale(horizontal, STICKER_HALF_SIZE)), _scale(vertical, STICKER_HALF_SIZE))
                output.append(
                    StickerGeometry(
                        index=sticker_index(face_index, row, col),
                        face=face,
                        row=row,
                        col=col,
                        sticker=str(stickers[row * 3 + col]),
                        center=center,
                        normal=normal,
                        corners=(lower_left, lower_right, upper_right, upper_left),
                    )
                )
    return tuple(output)


def animated_sticker_geometry(
    state: CubeState,
    token: str | None,
    progress: float,
) -> tuple[StickerGeometry, ...]:
    """Return animated geometry without changing ``state``.

    ``progress`` is clamped to 0..1.  At one, the returned moved stickers have
    made exactly the right-hand rotation described by ``cube_model``; callers
    can then switch to the already-computed next discrete ``CubeState``.
    """

    geometry = sticker_geometry(state)
    if token is None:
        return geometry
    axis, _, sign = _move_parts(token)
    clamped_progress = min(1.0, max(0.0, float(progress)))
    if clamped_progress == 0.0:
        return geometry
    angle = sign * (math.pi / 2.0) * clamped_progress
    affected = set(affected_sticker_indices(token))
    output: list[StickerGeometry] = []
    for sticker in geometry:
        if sticker.index not in affected:
            output.append(sticker)
            continue
        output.append(
            replace(
                sticker,
                center=rotate_point(sticker.center, axis, angle),
                normal=rotate_point(sticker.normal, axis, angle),
                corners=tuple(rotate_point(corner, axis, angle) for corner in sticker.corners),  # type: ignore[arg-type]
            )
        )
    return tuple(output)


STANDARD_STICKER_COLORS: dict[str, tuple[float, float, float]] = {
    "y": (0.96, 0.73, 0.15),
    "r": (0.88, 0.20, 0.18),
    "g": (0.16, 0.67, 0.36),
    "p": (0.56, 0.30, 0.76),
    "w": (0.94, 0.95, 0.97),
    "b": (0.16, 0.45, 0.82),
}


def sticker_color(sticker: str) -> tuple[float, float, float]:
    """Map standard course colors, or deterministically colour arbitrary labels."""

    # Only the exact lower-case course symbols use the familiar palette.
    # The input protocol also permits arbitrary printable ASCII labels, so
    # normalising case here would make valid distinct colors such as ``A``
    # and ``a`` visually indistinguishable.
    label = sticker if sticker else "?"
    if label in STANDARD_STICKER_COLORS:
        return STANDARD_STICKER_COLORS[label]

    # Legal input can use any six printable labels.  A stable HSL-like colour
    # keeps those states legible without adding a palette dependency.
    seed = sum((index + 1) * ord(character) for index, character in enumerate(label))
    hue = (seed * 0.618033988749895) % 1.0
    red = abs(hue * 6.0 - 3.0) - 1.0
    green = 2.0 - abs(hue * 6.0 - 2.0)
    blue = 2.0 - abs(hue * 6.0 - 4.0)
    return tuple(0.28 + 0.62 * min(1.0, max(0.0, channel)) for channel in (red, green, blue))  # type: ignore[return-value]


def _quad_vertices(corners: tuple[Vec3, Vec3, Vec3, Vec3], color: tuple[float, float, float]) -> Iterable[float]:
    """Flatten a counter-clockwise quad into two OpenGL triangles."""

    for corner in (corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]):
        yield corner[0]
        yield corner[1]
        yield corner[2]
        yield color[0]
        yield color[1]
        yield color[2]


def _body_vertices() -> Iterable[float]:
    """Dark cube shell behind stickers, so the seams remain clearly visible."""

    half = CUBIE_HALF_SIZE * 3.0 + 0.02
    color = (0.045, 0.055, 0.075)
    faces = (
        ((half, -half, -half), (half, half, -half), (half, half, half), (half, -half, half)),
        ((-half, -half, half), (-half, half, half), (-half, half, -half), (-half, -half, -half)),
        ((-half, half, -half), (-half, half, half), (half, half, half), (half, half, -half)),
        ((-half, -half, half), (-half, -half, -half), (half, -half, -half), (half, -half, half)),
        ((-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half)),
        ((half, -half, -half), (-half, -half, -half), (-half, half, -half), (half, half, -half)),
    )
    for face in faces:
        yield from _quad_vertices(face, color)


def scene_vertex_data(state: CubeState, token: str | None = None, progress: float = 0.0) -> tuple[bytes, int]:
    """Build interleaved ``position,rgb`` data for a full OpenGL frame.

    This remains a pure helper; it makes it possible to inspect the renderer's
    complete 54-sticker draw payload without creating a widget.
    """

    floats = array("f")
    floats.extend(_body_vertices())
    for sticker in animated_sticker_geometry(state, token, progress):
        floats.extend(_quad_vertices(sticker.corners, sticker_color(sticker.sticker)))
    return floats.tobytes(), len(floats) // 6


# Keep importing this module possible in a test runner that has not installed
# PySide6 yet.  The pure helpers above remain fully usable; only constructing a
# CubeView gives a targeted dependency error.
try:  # pragma: no cover - depends on the optional desktop package.
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMatrix4x4, QSurfaceFormat, QVector3D
    from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject
    from PySide6.QtOpenGLWidgets import QOpenGLWidget

    PYSIDE6_AVAILABLE = True
    _PYSIDE6_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - this environment intentionally has no GUI package.
    QPointF = object  # type: ignore[assignment,misc]
    Qt = object  # type: ignore[assignment,misc]
    QMatrix4x4 = object  # type: ignore[assignment,misc]
    QSurfaceFormat = object  # type: ignore[assignment,misc]
    QOpenGLBuffer = object  # type: ignore[assignment,misc]
    QOpenGLShader = object  # type: ignore[assignment,misc]
    QOpenGLShaderProgram = object  # type: ignore[assignment,misc]
    QOpenGLVertexArrayObject = object  # type: ignore[assignment,misc]
    QVector3D = object  # type: ignore[assignment,misc]
    QOpenGLWidget = object  # type: ignore[assignment,misc]
    PYSIDE6_AVAILABLE = False
    _PYSIDE6_IMPORT_ERROR = exc


GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_DEPTH_TEST = 0x0B71
GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004

_VERTEX_SHADER = """
#version 150
in vec3 a_position;
in vec3 a_color;
uniform mat4 u_mvp;
out vec3 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_position, 1.0);
    v_color = a_color;
}
"""

_FRAGMENT_SHADER = """
#version 150
in vec3 v_color;
out vec4 fragment_color;
void main() {
    fragment_color = vec4(v_color, 1.0);
}
"""


def _requested_surface_format() -> object:
    """Return the one desktop-OpenGL format used by this visualizer.

    Keeping the request in one place matters on macOS: Qt creates internal
    compositing contexts as the application starts, and those must use a
    shareable format matching the QOpenGLWidget's core-profile context.
    """

    if not PYSIDE6_AVAILABLE:
        raise RuntimeError("PySide6 is required to configure the OpenGL surface format.")
    surface_format = QSurfaceFormat()
    surface_format.setVersion(3, 2)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    return surface_format


def configure_opengl_surface_format() -> None:
    """Set the global core-profile request before QApplication is constructed.

    Qt documents this ordering as mandatory on some macOS configurations when
    a core profile is requested; it avoids an unshared fallback context.
    """

    if PYSIDE6_AVAILABLE:
        QSurfaceFormat.setDefaultFormat(_requested_surface_format())


class CubeView(QOpenGLWidget):
    """An orbitable OpenGL view of a ``CubeState`` and its current turn."""

    def __init__(self, parent: object | None = None, state: CubeState | None = None) -> None:
        if not PYSIDE6_AVAILABLE:
            raise RuntimeError(
                "CubeView requires PySide6. Install cube/visualizer/requirements.txt first."
            ) from _PYSIDE6_IMPORT_ERROR
        super().__init__(parent)  # type: ignore[misc]
        # Keep this explicit for callers that construct CubeView outside of
        # app.main().  Normal launches have already installed the same format
        # globally before QApplication is created.
        self.setFormat(_requested_surface_format())
        self._state = state if state is not None else CubeState.solved()
        self._animation_token: str | None = None
        self._animation_progress = 0.0
        self._yaw_degrees = 42.0
        self._pitch_degrees = 24.0
        self._distance = 8.2
        self._last_mouse_position: QPointF | None = None
        self._program: QOpenGLShaderProgram | None = None
        self._vertex_buffer: QOpenGLBuffer | None = None
        self._vertex_array: QOpenGLVertexArrayObject | None = None
        self._position_attribute = -1
        self._color_attribute = -1

        self.setMinimumSize(460, 460)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def state(self) -> CubeState:
        """The discrete model state currently being visualised."""

        return self._state

    def set_state(self, state: CubeState) -> None:
        """Display a discrete state and clear any in-flight visual turn."""

        self._state = state
        self._animation_token = None
        self._animation_progress = 0.0
        self.update()

    def set_animation(self, state: CubeState, token: str | None, progress: float) -> None:
        """Show ``state`` with ``token`` partially rotated, without mutating it."""

        if token is not None:
            # Validate immediately, which gives the controller a useful error
            # before it schedules an animation timer.
            _move_parts(token)
        self._state = state
        self._animation_token = token
        self._animation_progress = min(1.0, max(0.0, float(progress)))
        self.update()

    def reset_camera(self) -> None:
        """Restore the standard three-face teaching view."""

        self._yaw_degrees = 42.0
        self._pitch_degrees = 24.0
        self._distance = 8.2
        self.update()

    def initializeGL(self) -> None:  # noqa: N802 - Qt callback name.
        functions = self.context().functions()
        functions.glClearColor(0.075, 0.09, 0.125, 1.0)
        functions.glEnable(GL_DEPTH_TEST)

        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER):
            raise RuntimeError(f"could not compile cube vertex shader: {program.log()}")
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT_SHADER):
            raise RuntimeError(f"could not compile cube fragment shader: {program.log()}")
        if not program.link():
            raise RuntimeError(f"could not link cube shader program: {program.log()}")

        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not buffer.create():
            raise RuntimeError("could not create cube OpenGL vertex buffer")
        buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)
        vertex_array = QOpenGLVertexArrayObject(self)
        if not vertex_array.create():
            raise RuntimeError("could not create cube OpenGL vertex-array object")

        self._program = program
        self._vertex_buffer = buffer
        self._vertex_array = vertex_array
        self._position_attribute = program.attributeLocation("a_position")
        self._color_attribute = program.attributeLocation("a_color")

    def _mvp_matrix(self) -> QMatrix4x4:
        aspect = max(1, self.width()) / max(1, self.height())
        projection = QMatrix4x4()
        projection.perspective(38.0, aspect, 0.1, 100.0)

        yaw = math.radians(self._yaw_degrees)
        pitch = math.radians(self._pitch_degrees)
        eye = QVector3D(
            self._distance * math.cos(pitch) * math.sin(yaw),
            self._distance * math.sin(pitch),
            self._distance * math.cos(pitch) * math.cos(yaw),
        )
        view = QMatrix4x4()
        view.lookAt(eye, QVector3D(0.0, 0.0, 0.0), QVector3D(0.0, 1.0, 0.0))
        return projection * view

    def paintGL(self) -> None:  # noqa: N802 - Qt callback name.
        if self._program is None or self._vertex_buffer is None or self._vertex_array is None:
            return

        functions = self.context().functions()
        # QOpenGLWidget has already bound its FBO and configured a viewport
        # in physical pixels.  Do not replace it with QWidget's logical size:
        # doing so corrupts the compositor on Retina/high-DPI screens.
        functions.glClearColor(0.075, 0.09, 0.125, 1.0)
        functions.glEnable(GL_DEPTH_TEST)
        functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        vertex_bytes, vertex_count = scene_vertex_data(
            self._state, self._animation_token, self._animation_progress
        )

        self._program.bind()
        self._program.setUniformValue("u_mvp", self._mvp_matrix())
        self._vertex_array.bind()
        self._vertex_buffer.bind()
        self._vertex_buffer.allocate(vertex_bytes, len(vertex_bytes))
        stride = 6 * 4  # six float32 values: xyz, rgb.
        self._program.enableAttributeArray(self._position_attribute)
        self._program.setAttributeBuffer(self._position_attribute, GL_FLOAT, 0, 3, stride)
        self._program.enableAttributeArray(self._color_attribute)
        self._program.setAttributeBuffer(self._color_attribute, GL_FLOAT, 3 * 4, 3, stride)
        functions.glDrawArrays(GL_TRIANGLES, 0, vertex_count)
        self._program.disableAttributeArray(self._position_attribute)
        self._program.disableAttributeArray(self._color_attribute)
        self._vertex_buffer.release()
        self._vertex_array.release()
        self._program.release()

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse_position = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        if self._last_mouse_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = event.position()
            delta = current - self._last_mouse_position
            self._last_mouse_position = current
            self._yaw_degrees += delta.x() * 0.55
            self._pitch_degrees = min(85.0, max(-85.0, self._pitch_degrees + delta.y() * 0.55))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse_position = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        delta = event.angleDelta().y()
        if delta:
            # Positive wheel movement zooms towards the cube.  Fractional
            # trackpad deltas remain smooth because the exponent is continuous.
            self._distance *= math.pow(0.88, delta / 120.0)
            self._distance = min(18.0, max(4.4, self._distance))
            self.update()
            event.accept()
            return
        super().wheelEvent(event)
