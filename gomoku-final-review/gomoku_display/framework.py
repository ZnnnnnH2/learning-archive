"""Freeze the course-supplied C++ framework and call its legal-move library."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

FROZEN_FILES = ("include/gomoku.hpp", "include/student_api.hpp", "src/main.cpp")


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in FROZEN_FILES:
        content = (root / relative).read_bytes()
        digest.update(relative.encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def freeze_framework(source_root: Path, data_dir: Path) -> dict[str, str]:
    source_root = source_root.resolve()
    for relative in FROZEN_FILES:
        if not (source_root / relative).is_file():
            raise FileNotFoundError(source_root / relative)
    digest = tree_hash(source_root)
    target = data_dir / "framework" / digest
    if not target.exists():
        for relative in FROZEN_FILES:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, destination)
    manifest = {"source_root": str(source_root), "sha256": digest, "snapshot": str(target)}
    (data_dir / "framework.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def locked_framework(data_dir: Path) -> dict[str, str]:
    manifest_path = data_dir / "framework.json"
    if not manifest_path.exists():
        raise RuntimeError("framework is not initialized")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = Path(manifest["snapshot"])
    if tree_hash(snapshot) != manifest["sha256"]:
        raise RuntimeError("frozen framework snapshot hash mismatch")
    return manifest


def build_legal_probe(data_dir: Path, cxx: str = "c++") -> Path:
    manifest = locked_framework(data_dir)
    snapshot = Path(manifest["snapshot"])
    output = snapshot / "legal_probe"
    source = Path(__file__).with_name("legal_probe.cpp")
    if output.exists():
        return output
    result = subprocess.run([cxx, "-std=c++17", "-O2", "-I", str(snapshot / "include"),
                             str(source), "-o", str(output)], text=True,
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("cannot compile legal probe:\n" + result.stderr)
    return output


def legal_from_course(data_dir: Path, rows: list[str], x: int, y: int, color: str) -> dict[str, object]:
    if len(rows) != 15 or any(len(row) != 15 for row in rows):
        raise ValueError("expected 15 rows of length 15")
    probe = build_legal_probe(data_dir)
    text = "\n".join([*rows, f"{x} {y} {color}"]) + "\n"
    result = subprocess.run([str(probe)], input=text, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "course legal probe failed")
    return json.loads(result.stdout)
