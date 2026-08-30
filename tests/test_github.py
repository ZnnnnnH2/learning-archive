from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gomoku_display.github import normalize_public_repo_url, select_submission_file


class GitHubImportTests(unittest.TestCase):
    def test_public_repository_url_is_normalized(self) -> None:
        self.assertEqual(normalize_public_repo_url("https://github.com/classroom/anything.git"),
                         "https://github.com/classroom/anything.git")
        self.assertEqual(normalize_public_repo_url("https://github.com/classroom/anything"),
                         "https://github.com/classroom/anything.git")
        with self.assertRaises(ValueError):
            normalize_public_repo_url("git@github.com:classroom/anything.git")
        with self.assertRaises(ValueError):
            normalize_public_repo_url("https://github.com/classroom/anything/tree/main")

    def test_arbitrarily_named_cpp_is_discovered_or_explicitly_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "nested").mkdir()
            source = repo / "nested" / "unrelated-name.cpp"
            source.write_text('#include "student_api.hpp"\nnamespace gomoku { Move chooseMove(const Position& p) { return {0,0}; } }')
            self.assertEqual(select_submission_file(repo), source.resolve())
            other = repo / "other.cpp"; other.write_text(source.read_text())
            with self.assertRaises(ValueError):
                select_submission_file(repo)
            self.assertEqual(select_submission_file(repo, "other.cpp"), other.resolve())
