"""Docker compile/run boundary.  No shell is used for student code."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TurnOutput:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def think_us(self) -> int:
        values = re.findall(r"(?m)^THINK_TIME_US ([0-9]+)$", self.stderr)
        # The frozen main writes this line after chooseMove returns. Student debug
        # output happens during chooseMove, so only the final marker is trusted.
        return int(values[-1]) if values else 0


class DockerRunner:
    def __init__(self, data_dir: Path, image: str = "gcc:13") -> None:
        self.data_dir = data_dir
        self.image = image
        self.artifacts = data_dir / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read_limited(path: Path, limit: int = 1024 * 1024) -> str:
        if path.stat().st_size > limit:
            return path.read_bytes()[:limit].decode("utf-8", "replace") + "\n[OUTPUT_TRUNCATED]"
        return path.read_text(encoding="utf-8", errors="replace")

    def _run_limited(self, command: list[str], input_text: str, timeout: float) -> TurnOutput:
        with tempfile.TemporaryDirectory(prefix="gomoku-run-") as temp:
            root = Path(temp); out_path, err_path = root / "stdout", root / "stderr"
            with out_path.open("wb") as stdout, err_path.open("wb") as stderr:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
                try:
                    process.communicate(input_text.encode(), timeout=timeout)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    process.kill(); process.communicate(); timed_out = True
            return TurnOutput(process.returncode, self._read_limited(out_path), self._read_limited(err_path), timed_out)

    def compile(self, student_id: str, source: Path, framework_snapshot: Path) -> tuple[bool, str, Path | None]:
        target = self.artifacts / student_id
        target.mkdir(parents=True, exist_ok=True)
        output = target / "gomoku_player"
        command = ["docker", "run", "--rm", "--network", "none", "--cpus", "1", "--memory", "512m",
                   "--pids-limit", "64", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
                   "-v", f"{source.resolve()}:/submission/student.cpp:ro",
                   "-v", f"{framework_snapshot.resolve()}:/framework:ro",
                   "-v", f"{target.resolve()}:/out:rw", self.image, "g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
                   "-I", "/framework/include", "/framework/src/main.cpp", "/submission/student.cpp", "-o", "/out/gomoku_player"]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        log = (result.stdout + result.stderr)[-1024 * 1024:]
        return result.returncode == 0 and output.exists(), log, output if output.exists() else None

    def turn(self, binary: Path, position: str) -> TurnOutput:
        command = ["docker", "run", "--rm", "-i", "--network", "none", "--cpus", "1", "--memory", "512m",
                   "--pids-limit", "64", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                   "-v", f"{binary.parent.resolve()}:/run:ro", "--workdir", "/run", self.image,
                   "timeout", "--kill-after=0.1s", "2.1s", "./gomoku_player"]
        return self._run_limited(command, position, timeout=5.0)


def copy_submission(source: Path, target_dir: Path, student_id: str | None = None) -> tuple[str, Path]:
    student_id = student_id or source.stem
    if not student_id.isdigit():
        raise ValueError(f"student_id must be numeric: {student_id}")
    if source.suffix.lower() != ".cpp":
        raise ValueError(f"submission must be a .cpp file: {source.name}")
    target_dir.mkdir(parents=True, exist_ok=True)
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    target = target_dir / f"{student_id}.cpp"
    target.write_bytes(content)
    return digest, target
