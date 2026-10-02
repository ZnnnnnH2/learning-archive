"""SQLite persistence and append-only audit events."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class EventStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "event.sqlite3"
        self.log_path = data_dir / "events.jsonl"
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS player (
          student_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, roster_order INTEGER NOT NULL,
          github_url TEXT, submission_path TEXT);
        CREATE TABLE IF NOT EXISTS submission (
          student_id TEXT PRIMARY KEY REFERENCES player(student_id), source_path TEXT NOT NULL,
          sha256 TEXT NOT NULL, status TEXT NOT NULL, compile_log TEXT NOT NULL DEFAULT '', binary_path TEXT);
        CREATE TABLE IF NOT EXISTS tournament (
          id INTEGER PRIMARY KEY CHECK(id = 1), seed INTEGER NOT NULL, phase TEXT NOT NULL,
          manifest_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS group_member (
          group_name TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES player(student_id),
          draw_index INTEGER NOT NULL, PRIMARY KEY(group_name, student_id));
        CREATE TABLE IF NOT EXISTS pairing (
          id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL, group_name TEXT,
          round_no INTEGER NOT NULL, board_no INTEGER NOT NULL, left_id TEXT NOT NULL,
          right_id TEXT NOT NULL, opening_id INTEGER NOT NULL, symmetry INTEGER NOT NULL,
          state TEXT NOT NULL DEFAULT 'PENDING');
        CREATE TABLE IF NOT EXISTS game (
          id INTEGER PRIMARY KEY AUTOINCREMENT, pairing_id INTEGER NOT NULL REFERENCES pairing(id),
          game_no INTEGER NOT NULL, black_id TEXT NOT NULL, white_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'PENDING', result TEXT, winner_id TEXT,
          black_points REAL NOT NULL DEFAULT 0, white_points REAL NOT NULL DEFAULT 0,
          black_think_us INTEGER NOT NULL DEFAULT 0, white_think_us INTEGER NOT NULL DEFAULT 0,
          started_at TEXT, ended_at TEXT, UNIQUE(pairing_id, game_no));
        CREATE TABLE IF NOT EXISTS turn (
          id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER NOT NULL REFERENCES game(id), ply INTEGER NOT NULL,
          color TEXT NOT NULL, student_id TEXT NOT NULL, x INTEGER, y INTEGER, think_us INTEGER NOT NULL DEFAULT 0,
          board_before TEXT NOT NULL, reason TEXT, stdout TEXT NOT NULL DEFAULT '', stderr TEXT NOT NULL DEFAULT '',
          UNIQUE(game_id, ply));
        CREATE TABLE IF NOT EXISTS audit_event (
          id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS elimination_match (
          code TEXT PRIMARY KEY, left_id TEXT NOT NULL, right_id TEXT NOT NULL, round_name TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'PENDING', tie_round INTEGER NOT NULL DEFAULT 0);
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(player)")}
        if "github_url" not in columns:
            self.connection.execute("ALTER TABLE player ADD COLUMN github_url TEXT")
        if "submission_path" not in columns:
            self.connection.execute("ALTER TABLE player ADD COLUMN submission_path TEXT")
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def audit(self, kind: str, payload: dict[str, Any]) -> None:
        item = {"at": self._now(), "kind": kind, "payload": payload}
        with self.connection:
            self.connection.execute("INSERT INTO audit_event(at,kind,payload_json) VALUES (?,?,?)",
                                    (item["at"], kind, json.dumps(payload, ensure_ascii=False, sort_keys=True)))
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    def replace_roster(self, players: Iterable[tuple[str, str] | tuple[str, str, str | None, str | None]]) -> None:
        rows = [(row[0], row[1], row[2] if len(row) > 2 else None, row[3] if len(row) > 3 else None)
                for row in players]
        if not rows:
            raise ValueError("roster is empty")
        if len({row[0] for row in rows}) != len(rows):
            raise ValueError("duplicate student_id in roster")
        with self.connection:
            self.connection.execute("DELETE FROM submission")
            self.connection.execute("DELETE FROM player")
            self.connection.executemany("""INSERT INTO player(student_id,display_name,roster_order,github_url,submission_path)
                VALUES (?,?,?,?,?)""", [(identifier, name or identifier, index, github_url, submission_path)
                                           for index, (identifier, name, github_url, submission_path) in enumerate(rows)])
        self.audit("ROSTER_IMPORTED", {"count": len(rows)})

    def players(self) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM player ORDER BY roster_order").fetchall()

    def upsert_submission(self, student_id: str, source_path: str, digest: str, status: str,
                          compile_log: str = "", binary_path: str | None = None) -> None:
        with self.connection:
            self.connection.execute("""INSERT INTO submission(student_id,source_path,sha256,status,compile_log,binary_path)
                VALUES (?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET source_path=excluded.source_path,
                sha256=excluded.sha256,status=excluded.status,compile_log=excluded.compile_log,binary_path=excluded.binary_path""",
                (student_id, source_path, digest, status, compile_log, binary_path))
        self.audit("SUBMISSION_UPDATED", {"student_id": student_id, "status": status})

    def ready_students(self) -> list[str]:
        return [row[0] for row in self.connection.execute(
            "SELECT student_id FROM submission WHERE status='READY' ORDER BY student_id")]

    def save_draw(self, seed: int, manifest: dict[str, Any], groups: dict[str, list[str]],
                  pairings: Iterable[dict[str, Any]]) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM turn"); self.connection.execute("DELETE FROM game")
            self.connection.execute("DELETE FROM pairing"); self.connection.execute("DELETE FROM group_member")
            self.connection.execute("INSERT INTO tournament(id,seed,phase,manifest_json) VALUES(1,?,?,?) "
                                    "ON CONFLICT(id) DO UPDATE SET seed=excluded.seed,phase=excluded.phase,manifest_json=excluded.manifest_json",
                                    (seed, "GROUP", json.dumps(manifest, ensure_ascii=False, sort_keys=True)))
            for group_name, members in groups.items():
                self.connection.executemany("INSERT INTO group_member(group_name,student_id,draw_index) VALUES(?,?,?)",
                                            [(group_name, identifier, index) for index, identifier in enumerate(members)])
            for pairing in pairings:
                cursor = self.connection.execute("""INSERT INTO pairing(stage,group_name,round_no,board_no,left_id,right_id,opening_id,symmetry)
                    VALUES('GROUP',?,?,?,?,?,?,?)""", (pairing["group"], pairing["round"], pairing["board"],
                                                         pairing["left"], pairing["right"], pairing["opening"], pairing["symmetry"]))
                pairing_id = cursor.lastrowid
                for game_no, black, white in ((1, pairing["left"], pairing["right"]),
                                              (2, pairing["right"], pairing["left"])):
                    self.connection.execute("INSERT INTO game(pairing_id,game_no,black_id,white_id) VALUES(?,?,?,?)",
                                            (pairing_id, game_no, black, white))
        self.audit("DRAW_FROZEN", manifest)

    def state(self) -> dict[str, Any]:
        tournament = self.connection.execute("SELECT * FROM tournament WHERE id=1").fetchone()
        players = [dict(row) for row in self.connection.execute("""SELECT p.*, s.status AS submission_status
            FROM player p LEFT JOIN submission s USING(student_id) ORDER BY roster_order""")]
        groups = {name: [dict(row) for row in self.connection.execute("""SELECT p.student_id,p.display_name
            FROM group_member gm JOIN player p USING(student_id) WHERE gm.group_name=? ORDER BY gm.draw_index""", (name,))]
                  for name in "ABCD"}
        games = [dict(row) for row in self.connection.execute("""SELECT g.*, p.stage,p.group_name,p.round_no,p.board_no,
            p.opening_id,p.symmetry, pb.display_name AS black_name, pw.display_name AS white_name
            FROM game g JOIN pairing p ON p.id=g.pairing_id JOIN player pb ON pb.student_id=g.black_id
            JOIN player pw ON pw.student_id=g.white_id ORDER BY p.stage,p.group_name,p.round_no,p.board_no,g.game_no""")]
        rankings = {name: self.group_ranking(name) for name in "ABCD" if groups[name]}
        return {"tournament": dict(tournament) if tournament else None, "players": players,
                "groups": groups, "rankings": rankings, "games": games}

    def group_ranking(self, group_name: str) -> list[dict[str, Any]]:
        from .tournament import GameScore, standings
        members = [row[0] for row in self.connection.execute(
            "SELECT student_id FROM group_member WHERE group_name=? ORDER BY draw_index", (group_name,))]
        if not members:
            return []
        rows = self.connection.execute("""SELECT g.* FROM game g JOIN pairing p ON p.id=g.pairing_id
            WHERE p.stage='GROUP' AND p.group_name=? AND g.status='FINISHED'""", (group_name,)).fetchall()
        rank = standings(members, [GameScore(row["black_id"], row["white_id"], row["black_points"], row["white_points"],
                                              row["black_think_us"], row["white_think_us"]) for row in rows])
        names = {row["student_id"]: row["display_name"] for row in self.connection.execute(
            "SELECT student_id,display_name FROM player")}
        return [{"rank": index + 1, "student_id": item.student_id, "display_name": names[item.student_id],
                 "points": item.points, "wins": item.wins, "think_us": item.think_us}
                for index, item in enumerate(rank)]

    def has_elimination_match(self, code: str) -> bool:
        return bool(self.connection.execute("SELECT 1 FROM elimination_match WHERE code=?", (code,)).fetchone())

    def create_elimination_match(self, code: str, round_name: str, left_id: str, right_id: str,
                                 openings: list[tuple[int, int]]) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO elimination_match(code,left_id,right_id,round_name) VALUES(?,?,?,?)",
                                    (code, left_id, right_id, round_name))
            for index, (opening_id, symmetry) in enumerate(openings, 1):
                cursor = self.connection.execute("""INSERT INTO pairing(stage,group_name,round_no,board_no,left_id,right_id,opening_id,symmetry)
                    VALUES(?,NULL,?,?,?, ?,?,?)""", (code, index, 1, left_id, right_id, opening_id, symmetry))
                for game_no, black, white in ((1, left_id, right_id), (2, right_id, left_id)):
                    self.connection.execute("INSERT INTO game(pairing_id,game_no,black_id,white_id) VALUES(?,?,?,?)",
                                            (cursor.lastrowid, game_no, black, white))
        self.audit("ELIMINATION_MATCH_CREATED", {"code": code, "left": left_id, "right": right_id,
                                                   "openings": openings})

    def match_games(self, code: str) -> list[sqlite3.Row]:
        return self.connection.execute("""SELECT g.* FROM game g JOIN pairing p ON p.id=g.pairing_id
            WHERE p.stage=? ORDER BY p.round_no,g.game_no""", (code,)).fetchall()

    def add_tiebreak_pair(self, code: str, opening_id: int, symmetry: int) -> None:
        match = self.connection.execute("SELECT * FROM elimination_match WHERE code=?", (code,)).fetchone()
        if not match:
            raise KeyError(code)
        with self.connection:
            round_no = self.connection.execute("SELECT COALESCE(MAX(round_no),0)+1 FROM pairing WHERE stage=?", (code,)).fetchone()[0]
            cursor = self.connection.execute("""INSERT INTO pairing(stage,group_name,round_no,board_no,left_id,right_id,opening_id,symmetry)
                VALUES(?,NULL,?,?,?, ?,?,?)""", (code, round_no, 1, match["left_id"], match["right_id"], opening_id, symmetry))
            for game_no, black, white in ((1, match["left_id"], match["right_id"]), (2, match["right_id"], match["left_id"])):
                self.connection.execute("INSERT INTO game(pairing_id,game_no,black_id,white_id) VALUES(?,?,?,?)",
                                        (cursor.lastrowid, game_no, black, white))
            self.connection.execute("UPDATE elimination_match SET tie_round=tie_round+1,state='TIEBREAK' WHERE code=?", (code,))
        self.audit("TIEBREAK_ADDED", {"code": code, "opening_id": opening_id, "symmetry": symmetry})

    def game(self, game_id: int) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM game WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise KeyError(game_id)
        return row

    def turns(self, game_id: int) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM turn WHERE game_id=? ORDER BY ply", (game_id,)).fetchall()

    def start_game(self, game_id: int) -> None:
        with self.connection:
            self.connection.execute("UPDATE game SET status='RUNNING',started_at=? WHERE id=? AND status='PENDING'",
                                    (self._now(), game_id))
        self.audit("GAME_STARTED", {"game_id": game_id})

    def append_turn(self, game_id: int, ply: int, color: str, student_id: str, board_before: list[str],
                    x: int | None, y: int | None, think_us: int, reason: str | None,
                    stdout: str, stderr: str) -> None:
        with self.connection:
            self.connection.execute("""INSERT INTO turn(game_id,ply,color,student_id,x,y,think_us,board_before,reason,stdout,stderr)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (game_id, ply, color, student_id, x, y, think_us,
                                                      "\n".join(board_before), reason, stdout, stderr))
        self.audit("TURN", {"game_id": game_id, "ply": ply, "color": color, "student_id": student_id,
                             "move": [x, y] if x is not None else None, "think_us": think_us, "reason": reason})

    def finish_game(self, game_id: int, result: str, winner_id: str | None,
                    black_points: float, white_points: float, black_think_us: int, white_think_us: int) -> None:
        with self.connection:
            self.connection.execute("""UPDATE game SET status='FINISHED',result=?,winner_id=?,black_points=?,white_points=?,
                black_think_us=?,white_think_us=?,ended_at=? WHERE id=?""",
                (result, winner_id, black_points, white_points, black_think_us, white_think_us, self._now(), game_id))
        self.audit("GAME_FINISHED", {"game_id": game_id, "result": result, "winner_id": winner_id})
