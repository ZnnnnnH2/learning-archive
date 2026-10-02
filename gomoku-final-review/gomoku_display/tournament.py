"""Pure, deterministic tournament draw, schedule, and standings logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Iterable


class Pcg32:
    """Small specified PRNG; unlike random.shuffle this is cross-version stable."""
    def __init__(self, seed: int, sequence: int = 54) -> None:
        self.state = 0
        self.inc = (sequence << 1) | 1
        self.next_u32()
        self.state = (self.state + (seed & ((1 << 64) - 1))) & ((1 << 64) - 1)
        self.next_u32()

    def next_u32(self) -> int:
        old = self.state
        self.state = (old * 6364136223846793005 + self.inc) & ((1 << 64) - 1)
        xorshifted = ((old >> 18) ^ old) >> 27
        rotation = old >> 59
        return ((xorshifted >> rotation) | (xorshifted << ((-rotation) & 31))) & 0xFFFFFFFF

    def below(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        threshold = ((1 << 32) - bound) % bound
        while True:
            value = self.next_u32()
            if value >= threshold:
                return value % bound

    def shuffle(self, values: list[str]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.below(index + 1)
            values[index], values[other] = values[other], values[index]


@dataclass(frozen=True)
class Pairing:
    group: str
    round: int
    board: int
    left: str
    right: str


@dataclass(frozen=True)
class GameScore:
    black: str
    white: str
    black_points: float
    white_points: float
    black_think_us: int = 0
    white_think_us: int = 0


@dataclass
class Standing:
    student_id: str
    points: float = 0
    wins: int = 0
    think_us: int = 0
    h2h: dict[str, float] = field(default_factory=lambda: defaultdict(float))


def draw_groups(student_ids: Iterable[str], seed: int) -> dict[str, list[str]]:
    ids = sorted(student_ids)
    if len(ids) != 21:
        raise ValueError("the final-review format requires exactly 21 eligible students")
    rng = Pcg32(seed)
    rng.shuffle(ids)
    sizes = (("A", 6), ("B", 5), ("C", 5), ("D", 5))
    result: dict[str, list[str]] = {}
    start = 0
    for group, size in sizes:
        result[group] = ids[start:start + size]
        start += size
    return result


def round_robin(group: str, members: list[str]) -> list[Pairing]:
    """Circle method: 6-player and 5-player (with a BYE) groups both take 5 rounds."""
    if len(members) not in (5, 6):
        raise ValueError("groups must have five or six players")
    slots: list[str | None] = list(members)
    if len(slots) % 2:
        slots.append(None)
    pairings: list[Pairing] = []
    for round_index in range(len(slots) - 1):
        board = 1
        for index in range(len(slots) // 2):
            a, b = slots[index], slots[-1 - index]
            if a is not None and b is not None:
                # Alternate home side by round to avoid an arbitrary visual bias.
                left, right = (a, b) if round_index % 2 == 0 else (b, a)
                pairings.append(Pairing(group, round_index + 1, board, left, right))
                board += 1
        slots = [slots[0], slots[-1], *slots[1:-1]]
    return pairings


def standings(members: Iterable[str], games: Iterable[GameScore]) -> list[Standing]:
    table = {student_id: Standing(student_id) for student_id in members}
    for game in games:
        black, white = table[game.black], table[game.white]
        black.points += game.black_points
        white.points += game.white_points
        black.h2h[white.student_id] += game.black_points
        white.h2h[black.student_id] += game.white_points
        black.think_us += game.black_think_us
        white.think_us += game.white_think_us
        if game.black_points == 1:
            black.wins += 1
        if game.white_points == 1:
            white.wins += 1

    def sb(row: Standing) -> float:
        return sum(score * table[opponent].points for opponent, score in row.h2h.items())

    # Recursive tied-cohort head-to-head is represented by the tuple of scores
    # against opponents with the same overall score. The final ID ordering only
    # handles an exact microsecond tie after every published criterion.
    def sort_key(row: Standing) -> tuple[float, float, float, int, int, str]:
        peers = [candidate.student_id for candidate in table.values()
                 if candidate.student_id != row.student_id and candidate.points == row.points]
        mini = sum(row.h2h.get(peer, 0) for peer in peers)
        return (-row.points, -mini, -sb(row), -row.wins, row.think_us, row.student_id)

    return sorted(table.values(), key=sort_key)
