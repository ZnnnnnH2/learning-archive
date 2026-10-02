from __future__ import annotations

import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gobang_gui import GomokuState, StudentProgram, executable_problem  # noqa: E402


class ProgramInputTests(unittest.TestCase):
    def test_source_selection_still_requires_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "student.cp"
            source.write_text("int main() { return 0; }\n", encoding="utf-8")
            program = StudentProgram()
            self.addCleanup(program.close)

            ok, message = program.select_program(source)

            self.assertTrue(ok)
            self.assertTrue(program.needs_compilation)
            self.assertFalse(program.is_ready)
            self.assertIn("编译", message)

    def test_compiled_cpp_can_be_reselected_as_direct_program(self) -> None:
        if StudentProgram.find_compiler() is None:
            self.skipTest("本机没有可用的 C++ 编译器")
        builder = StudentProgram()
        direct = StudentProgram()
        self.addCleanup(builder.close)
        self.addCleanup(direct.close)
        source = Path(__file__).parent / "fixtures" / "forfeit_after_opening.cpp"
        builder.select_source(source)
        ok, log = builder.compile()
        self.assertTrue(ok, log)
        assert builder.executable_path is not None

        ok, message = direct.select_program(builder.executable_path)
        self.assertTrue(ok, message)
        self.assertFalse(direct.needs_compilation)

        request = GomokuState(board_size=9).request("direct-native", 2000)
        ok, log, response = direct.run_one_move(request, 2000, require_case_id=True)

        self.assertTrue(ok, log)
        self.assertEqual(response["move"], [4, 4])

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX executable fixture")
    def test_direct_executable_can_answer_a_move_without_compilation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "student-program"
            executable.write_text(
                f"#!{sys.executable}\n"
                + textwrap.dedent(
                    """
                    import json
                    import sys

                    request = json.loads(sys.stdin.readline())
                    print(json.dumps({"case_id": request["case_id"], "move": [4, 4]}))
                    """
                ),
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            program = StudentProgram()
            self.addCleanup(program.close)

            ok, message = program.select_program(executable)
            self.assertTrue(ok, message)
            self.assertFalse(program.needs_compilation)
            self.assertTrue(program.is_ready)

            request = GomokuState(board_size=9).request("direct-program", 2000)
            ok, log, response = program.run_one_move(request, 2000, require_case_id=True)

            self.assertTrue(ok, log)
            self.assertEqual(response["move"], [4, 4])

    def test_foreign_programs_are_rejected_with_platform_specific_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            windows_program = Path(directory) / "student.exe"
            windows_program.write_bytes(b"MZ" + b"unused")
            mac_program = Path(directory) / "student-mac"
            mac_program.write_bytes(b"\xcf\xfa\xed\xfe" + b"unused")

            self.assertIn(
                "Windows .exe",
                executable_problem(windows_program, host_platform="darwin") or "",
            )
            self.assertIn(
                "macOS 程序",
                executable_problem(mac_program, host_platform="win32") or "",
            )
            self.assertIsNone(executable_problem(windows_program, host_platform="win32"))

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX permission semantics")
    def test_non_executable_file_has_actionable_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            program_path = Path(directory) / "student-program"
            program_path.write_text("not executable\n", encoding="utf-8")
            program_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

            problem = executable_problem(program_path)

            self.assertIn("chmod +x", problem or "")


if __name__ == "__main__":
    unittest.main()
