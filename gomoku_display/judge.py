"""Trusted game loop: only this module changes an authoritative board."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from .framework import legal_from_course
from .openings import opening_by_id
from .runner import TurnOutput
from .store import EventStore

MOVE_RE = re.compile(r"\A\s*(-?\d+)\s*,\s*(-?\d+)\s*\Z")


class TurnRunner(Protocol):
    def turn(self, binary: Path, position: str) -> TurnOutput: ...


def blank_board() -> list[list[str]]:
    return [["." for _ in range(15)] for _ in range(15)]


def rows(board: list[list[str]]) -> list[str]:
    return ["".join(row) for row in board]


def position_text(board: list[list[str]], color: str, move_number: int, turn_ms: int, left_ms: int, seed: int) -> str:
    return "\n".join(["GOMOKU 15", *rows(board),
                      f"MY {color} SIDE {color} MOVE {move_number} TIME_TURN {turn_ms} TIME_LEFT {left_ms} SEED {seed}"]) + "\n"


def _reason(output: TurnOutput) -> str:
    if output.timed_out or output.exit_code == 124:
        return "TURN_TIMEOUT"
    match = re.findall(r"(?m)^TERMINAL_REASON ([A-Z_]+)$", output.stderr)
    if match:
        return match[-1]
    return "PROGRAM_EXIT" if output.exit_code else "INVALID_OUTPUT"


class Judge:
    def __init__(self, store: EventStore, data_dir: Path, runner: TurnRunner) -> None:
        self.store, self.data_dir, self.runner = store, data_dir, runner

    def run_game(self, game_id: int) -> str:
        game = self.store.game(game_id)
        details = self.store.connection.execute("""SELECT p.opening_id,p.symmetry,t.seed,sb.binary_path AS black_binary,
            sw.binary_path AS white_binary FROM game g JOIN pairing p ON p.id=g.pairing_id JOIN tournament t ON t.id=1
            JOIN submission sb ON sb.student_id=g.black_id JOIN submission sw ON sw.student_id=g.white_id WHERE g.id=?""", (game_id,)).fetchone()
        if not details or not details["black_binary"] or not details["white_binary"]:
            raise RuntimeError("both players must have preflighted binaries")
        board = blank_board()
        opening = opening_by_id(details["opening_id"]).moves(details["symmetry"])
        for index, (x, y) in enumerate(opening):
            color = "B" if index % 2 == 0 else "W"
            verdict = legal_from_course(self.data_dir, rows(board), x, y, color)
            if not verdict["legal"]:
                raise RuntimeError(f"opening {details['opening_id']} failed course validation: {verdict}")
            board[y][x] = color
        spent = {"B": 0, "W": 0}
        ids = {"B": game["black_id"], "W": game["white_id"]}
        binaries = {"B": Path(details["black_binary"]), "W": Path(details["white_binary"])}
        self.store.start_game(game_id)
        for ply in range(6, 201):
            color = "W" if ply % 2 == 0 else "B"
            remaining = max(0, 45_000_000 - spent[color])
            before = rows(board)
            output = self.runner.turn(binaries[color], position_text(board, color, ply - 1,
                                                                      min(2000, remaining // 1000), remaining // 1000,
                                                                      int(details["seed"])))
            move = MOVE_RE.fullmatch(output.stdout)
            reason: str | None = None
            x = y = None
            think_us = output.think_us
            if output.exit_code or output.timed_out or not move:
                reason = _reason(output)
            elif think_us > 2_000_000:
                reason = "TURN_TIMEOUT"
            elif think_us > remaining:
                reason = "MATCH_TIMEOUT"
            else:
                x, y = int(move.group(1)), int(move.group(2))
                verdict = legal_from_course(self.data_dir, before, x, y, color)
                if not verdict["legal"]:
                    reason = str(verdict["status"])
            self.store.append_turn(game_id, ply, color, ids[color], before, x, y, think_us, reason,
                                   output.stdout, output.stderr)
            spent[color] += think_us
            if reason:
                winner_color = "W" if color == "B" else "B"
                return self._finish(game_id, reason, ids[winner_color], game, spent)
            assert x is not None and y is not None
            board[y][x] = color
            terminal = str(verdict["result_after"])
            if terminal != "ONGOING":
                winner = ids["B"] if terminal == "BLACK_WIN" else ids["W"] if terminal == "WHITE_WIN" else None
                return self._finish(game_id, terminal, winner, game, spent)
        return self._finish(game_id, "DRAW", None, game, spent)

    def _finish(self, game_id: int, result: str, winner_id: str | None, game: object, spent: dict[str, int]) -> str:
        if winner_id == game["black_id"]:
            points = (1.0, 0.0)
        elif winner_id == game["white_id"]:
            points = (0.0, 1.0)
        else:
            points = (0.5, 0.5)
        self.store.finish_game(game_id, result, winner_id, *points, spent["B"], spent["W"])
        return result


def replay_game(store: EventStore, data_dir: Path, game_id: int) -> dict[str, object]:
    """Re-run every recorded move against the frozen course library, read-only."""
    game = store.game(game_id)
    pairing = store.connection.execute("SELECT opening_id,symmetry FROM pairing WHERE id=?", (game["pairing_id"],)).fetchone()
    board = blank_board()
    for index, (x, y) in enumerate(opening_by_id(pairing["opening_id"]).moves(pairing["symmetry"])):
        board[y][x] = "B" if index % 2 == 0 else "W"
    errors: list[str] = []
    moves: list[dict[str, object]] = []
    for turn in store.turns(game_id):
        if turn["x"] is None:
            break
        verdict = legal_from_course(data_dir, rows(board), turn["x"], turn["y"], turn["color"])
        if not verdict["legal"]:
            errors.append(f"ply {turn['ply']} no longer legal: {verdict['status']}")
            break
        board[turn["y"]][turn["x"]] = turn["color"]
        moves.append({"ply": turn["ply"], "color": turn["color"], "x": turn["x"], "y": turn["y"],
                      "think_us": turn["think_us"], "reason": turn["reason"]})
    return {"game_id": game_id, "ok": not errors, "errors": errors, "board": rows(board), "moves": moves,
            "opening_id": pairing["opening_id"], "symmetry": pairing["symmetry"]}
