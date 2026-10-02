"""Public GitHub submission acquisition without executing repository code."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .runner import copy_submission

IMPLEMENTATION_RE = re.compile(
    r"\b(?:gomoku::)?Move\s+(?:gomoku::)?chooseMove\s*\(\s*const\s+(?:gomoku::)?Position\s*&",
    re.MULTILINE,
)
SKIP_DIRS = {".git", "build", "cmake-build-debug", "cmake-build-release", "vendor", "third_party"}


@dataclass(frozen=True)
class GitHubImport:
    repo_url: str
    commit: str
    selected_path: str
    sha256: str
    stored_path: Path


def normalize_public_repo_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("github_url must be a public https://github.com/<owner>/<repo> URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        raise ValueError("github_url must name exactly one owner/repository")
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        raise ValueError("invalid GitHub repository URL")
    return f"https://github.com/{owner}/{repository}.git"


def select_submission_file(repository: Path, requested_path: str | None = None) -> Path:
    repository = repository.resolve()
    if requested_path:
        candidate = (repository / requested_path).resolve()
        if repository not in candidate.parents or candidate.suffix.lower() != ".cpp" or not candidate.is_file():
            raise ValueError("submission_path must be an existing .cpp file inside the repository")
        return candidate
    candidates: list[Path] = []
    for path in repository.rglob("*.cpp"):
        if any(part in SKIP_DIRS for part in path.relative_to(repository).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if IMPLEMENTATION_RE.search(text):
            candidates.append(path)
    if len(candidates) != 1:
        names = ", ".join(str(path.relative_to(repository)) for path in candidates) or "none"
        raise ValueError(f"found {len(candidates)} chooseMove candidates ({names}); set submission_path in roster.csv")
    return candidates[0]


def import_public_repository(student_id: str, github_url: str, submission_path: str | None,
                             target_dir: Path) -> GitHubImport:
    normalized = normalize_public_repo_url(github_url)
    workspace = target_dir / "github-clones"
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{student_id}-", dir=workspace) as temporary:
        repo = Path(temporary) / "repo"
        clone = subprocess.run(["git", "-c", "protocol.file.allow=never", "clone", "--depth=1", "--no-tags",
                                "--filter=blob:none", normalized, str(repo)], text=True, capture_output=True,
                               timeout=120, check=False)
        if clone.returncode:
            detail = (clone.stderr or clone.stdout).strip()[-2000:]
            raise RuntimeError(f"cannot clone public repository: {detail}")
        revision = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True,
                                  timeout=10, check=False)
        if revision.returncode:
            raise RuntimeError("cannot resolve cloned repository commit")
        chosen = select_submission_file(repo, submission_path)
        digest, stored = copy_submission(chosen, target_dir / "submissions", student_id)
        return GitHubImport(normalized, revision.stdout.strip(), str(chosen.relative_to(repo)), digest, stored)
