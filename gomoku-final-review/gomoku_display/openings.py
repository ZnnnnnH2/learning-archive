"""Official Gomocup 2026 Renju 15x15 five-move opening pool.

Coordinates are relative to the 15x15 centre (7, 7), and moves alternate
black/white/black/white/black.  Source: https://live.gomocup.org/openings/
"""

from __future__ import annotations

from dataclasses import dataclass

BOARD_SIZE = 15
CENTER = 7


@dataclass(frozen=True)
class Opening:
    id: int
    relative_moves: tuple[tuple[int, int], ...]

    def moves(self, symmetry: int = 0) -> tuple[tuple[int, int], ...]:
        return tuple(apply_symmetry(CENTER + x, CENTER + y, symmetry)
                     for x, y in self.relative_moves)


# Copied verbatim from the official 2026 Renju (15x15) list.
OPENINGS: tuple[Opening, ...] = (
    Opening(1, ((0, 0), (1, -1), (3, -1), (2, 0), (-1, -1))),
    Opening(2, ((0, 0), (1, -1), (3, -1), (3, 0), (-2, 0))),
    Opening(3, ((0, 0), (0, -1), (1, -3), (2, -2), (2, -3))),
    Opening(4, ((0, 0), (1, -1), (3, -2), (3, 0), (1, 1))),
    Opening(5, ((0, 0), (1, -1), (3, 1), (3, 0), (1, 1))),
    Opening(6, ((0, 0), (0, -1), (3, -1), (3, 0), (3, 1))),
    Opening(7, ((0, 0), (1, -1), (3, 2), (2, 1), (1, 3))),
    Opening(8, ((0, 0), (0, -1), (2, -3), (2, -2), (1, -2))),
    Opening(9, ((0, 0), (0, -1), (0, -3), (1, -3), (-2, 0))),
    Opening(10, ((0, 0), (1, -1), (3, -3), (3, -1), (0, -1))),
    Opening(11, ((0, 0), (0, -1), (3, -3), (2, -2), (1, -2))),
    Opening(12, ((0, 0), (0, -1), (3, -2), (2, -1), (1, -2))),
)


def apply_symmetry(x: int, y: int, symmetry: int) -> tuple[int, int]:
    """Apply one of D4's eight deterministic transforms around board centre."""
    if not 0 <= symmetry < 8:
        raise ValueError("symmetry must be 0..7")
    dx, dy = x - CENTER, y - CENTER
    if symmetry >= 4:
        dx = -dx
    turns = symmetry % 4
    for _ in range(turns):
        dx, dy = -dy, dx
    return CENTER + dx, CENTER + dy


def opening_by_id(opening_id: int) -> Opening:
    if not 1 <= opening_id <= len(OPENINGS):
        raise KeyError(opening_id)
    return OPENINGS[opening_id - 1]
