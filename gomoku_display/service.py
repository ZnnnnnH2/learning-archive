"""Application service used by both CLI and browser control console."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

from .framework import locked_framework
from .github import import_public_repository
from .judge import Judge, replay_game
from .runner import DockerRunner, copy_submission
from .store import EventStore
from .tournament import Pcg32, draw_groups, round_robin


class TournamentService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()
        self.store = EventStore(self.data_dir)

    def import_roster(self, csv_path: Path) -> int:
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "student_id" not in reader.fieldnames:
                raise ValueError("roster.csv needs a student_id column")
            rows = []
            for row in reader:
                student_id = (row.get("student_id") or "").strip()
                if not student_id.isdigit():
                    raise ValueError(f"student_id must be digits: {student_id!r}")
                rows.append((student_id, (row.get("display_name") or student_id).strip(),
                             (row.get("github_url") or "").strip() or None,
                             (row.get("submission_path") or "").strip() or None))
        self.store.replace_roster(rows)
        return len(rows)

    def import_submissions(self, source_dir: Path) -> dict[str, int]:
        roster = {row["student_id"] for row in self.store.players()}
        seen: set[str] = set(); summary = {"imported": 0, "rejected": 0}
        for source in sorted(source_dir.glob("*.cpp")):
            student_id = source.stem
            if not student_id.isdigit() or student_id not in roster or student_id in seen:
                summary["rejected"] += 1
                continue
            seen.add(student_id)
            digest, target = copy_submission(source, self.data_dir / "submissions", student_id)
            self.store.upsert_submission(student_id, str(target), digest, "IMPORTED")
            summary["imported"] += 1
        return summary

    def import_github(self) -> dict[str, int]:
        """Fetch each rostered public repository; arbitrary repo/file names are supported."""
        summary = {"imported": 0, "rejected": 0, "missing_url": 0}
        for player in self.store.players():
            github_url = player["github_url"]
            if not github_url:
                summary["missing_url"] += 1
                continue
            try:
                imported = import_public_repository(player["student_id"], github_url, player["submission_path"], self.data_dir)
                self.store.upsert_submission(player["student_id"], str(imported.stored_path), imported.sha256, "IMPORTED")
                self.store.audit("GITHUB_IMPORTED", {"student_id": player["student_id"], "repo_url": imported.repo_url,
                    "commit": imported.commit, "submission_path": imported.selected_path, "sha256": imported.sha256})
                summary["imported"] += 1
            except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                self.store.upsert_submission(player["student_id"], github_url, "", "DQ", str(error))
                summary["rejected"] += 1
        return summary

    def preflight(self, image: str = "gcc:13") -> dict[str, int]:
        framework = locked_framework(self.data_dir)
        runner = DockerRunner(self.data_dir, image)
        result = {"ready": 0, "dq": 0}
        for submission in self.store.connection.execute("SELECT * FROM submission ORDER BY student_id"):
            source = Path(submission["source_path"])
            ok, log, binary = runner.compile(submission["student_id"], source, Path(framework["snapshot"]))
            self.store.upsert_submission(submission["student_id"], str(source), submission["sha256"],
                                         "READY" if ok else "DQ", log, str(binary) if binary else None)
            result["ready" if ok else "dq"] += 1
        return result

    def draw(self, seed: int) -> dict[str, list[str]]:
        framework = locked_framework(self.data_dir)
        students = self.store.ready_students()
        groups = draw_groups(students, seed)
        rng = Pcg32(seed, sequence=0xC0DE)
        fixtures: list[dict[str, int | str]] = []
        for group, members in groups.items():
            for pairing in round_robin(group, members):
                fixtures.append({"group": group, "round": pairing.round, "board": pairing.board,
                                 "left": pairing.left, "right": pairing.right,
                                 "opening": rng.below(12) + 1, "symmetry": rng.below(8)})
        manifest = {"seed": seed, "framework_sha256": framework["sha256"], "eligible_students": students,
                    "groups": groups, "openings": "gomocup-2026-renju15-12", "prng": "PCG32-v1"}
        self.store.save_draw(seed, manifest, groups, fixtures)
        return groups

    def run_game(self, game_id: int, image: str = "gcc:13") -> str:
        return Judge(self.store, self.data_dir, DockerRunner(self.data_dir, image)).run_game(game_id)

    def advance_knockout(self) -> str:
        """Create the next elimination round, or append the prescribed tiebreak."""
        tournament = self.store.connection.execute("SELECT seed FROM tournament WHERE id=1").fetchone()
        if not tournament:
            raise RuntimeError("draw a tournament first")
        seed = int(tournament["seed"])
        group_pending = self.store.connection.execute("""SELECT COUNT(*) FROM game g JOIN pairing p ON p.id=g.pairing_id
            WHERE p.stage='GROUP' AND g.status!='FINISHED'""").fetchone()[0]
        if not self.store.has_elimination_match("QF1"):
            if group_pending:
                raise RuntimeError("finish every group game before creating quarterfinals")
            ranks = {name: self.store.group_ranking(name) for name in "ABCD"}
            if any(len(rows) < 2 for rows in ranks.values()):
                raise RuntimeError("every group needs two ranked players")
            pairs = [("QF1", "QF", ranks["A"][0]["student_id"], ranks["B"][1]["student_id"]),
                     ("QF2", "QF", ranks["C"][0]["student_id"], ranks["D"][1]["student_id"]),
                     ("QF3", "QF", ranks["B"][0]["student_id"], ranks["A"][1]["student_id"]),
                     ("QF4", "QF", ranks["D"][0]["student_id"], ranks["C"][1]["student_id"])]
            for index, (code, label, left, right) in enumerate(pairs):
                self.store.create_elimination_match(code, label, left, right, self._openings(seed, code, 2))
            return "QUARTERFINALS_CREATED"
        qf = [self._resolve_or_tiebreak(f"QF{number}", seed) for number in range(1, 5)]
        if any(winner is None for winner in qf):
            return "WAITING_FOR_QUARTERFINALS"
        if not self.store.has_elimination_match("SF1"):
            self.store.create_elimination_match("SF1", "SF", qf[0], qf[1], self._openings(seed, "SF1", 2))
            self.store.create_elimination_match("SF2", "SF", qf[2], qf[3], self._openings(seed, "SF2", 2))
            return "SEMIFINALS_CREATED"
        sf = [self._resolve_or_tiebreak(f"SF{number}", seed) for number in range(1, 3)]
        if any(winner is None for winner in sf):
            return "WAITING_FOR_SEMIFINALS"
        if not self.store.has_elimination_match("FINAL"):
            self.store.create_elimination_match("FINAL", "FINAL", sf[0], sf[1], self._openings(seed, "FINAL", 3))
            return "FINAL_CREATED"
        winner = self._resolve_or_tiebreak("FINAL", seed)
        return "CHAMPION:" + winner if winner else "WAITING_FOR_FINAL"

    @staticmethod
    def _code_seed(seed: int, code: str) -> int:
        return seed ^ int.from_bytes(hashlib.sha256(code.encode()).digest()[:8], "big")

    def _openings(self, seed: int, code: str, count: int, used: set[int] | None = None) -> list[tuple[int, int]]:
        rng = Pcg32(self._code_seed(seed, code), sequence=0x51DE)
        identifiers = list(range(1, 13)); rng.shuffle(identifiers)
        selected = [identifier for identifier in identifiers if not used or identifier not in used][:count]
        return [(identifier, rng.below(8)) for identifier in selected]

    def _resolve_or_tiebreak(self, code: str, seed: int) -> str | None:
        match = self.store.connection.execute("SELECT * FROM elimination_match WHERE code=?", (code,)).fetchone()
        if not match:
            raise RuntimeError(f"missing {code}")
        games = self.store.match_games(code)
        if any(game["status"] != "FINISHED" for game in games):
            return None
        score = {match["left_id"]: 0.0, match["right_id"]: 0.0}
        white_score = {match["left_id"]: 0.0, match["right_id"]: 0.0}
        time = {match["left_id"]: 0, match["right_id"]: 0}
        for game in games:
            score[game["black_id"]] += game["black_points"]; score[game["white_id"]] += game["white_points"]
            white_score[game["white_id"]] += game["white_points"]
            time[game["black_id"]] += game["black_think_us"]; time[game["white_id"]] += game["white_think_us"]
        left, right = match["left_id"], match["right_id"]
        if score[left] != score[right]:
            return left if score[left] > score[right] else right
        if match["tie_round"] < 3:
            used = {row[0] for row in self.store.connection.execute("SELECT opening_id FROM pairing WHERE stage=?", (code,))}
            opening, symmetry = self._openings(seed, code, 1, used)[0]
            self.store.add_tiebreak_pair(code, opening, symmetry)
            return None
        if white_score[left] != white_score[right]:
            return left if white_score[left] > white_score[right] else right
        if time[left] != time[right]:
            return left if time[left] < time[right] else right
        return min(left, right)

    def replay(self, game_id: int) -> dict[str, object]:
        return replay_game(self.store, self.data_dir, game_id)

    def close(self) -> None:
        self.store.close()
