"""Regressions for TypeScript diagnostic filtering and compiler failures."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TypeScriptDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "tsconfig.json").write_text("{}")
        self.source = self.project / "file.ts"
        self.source.write_text("const value: number = 1;\n")
        tools = self.project / "tools"
        tools.mkdir()
        compiler = tools / "tsc"
        compiler.write_text(
            '#!/bin/sh\nprintf "%s" "$TSC_OUTPUT"\nexit "$TSC_STATUS"\n'
        )
        compiler.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}")

    def check_compiler(self, output, status, expected):
        result = subprocess.run(
            ["bash", str(ROOT / "bin/typecheck-file"), str(self.source)],
            env=dict(self.env, TSC_OUTPUT=output, TSC_STATUS=str(status)),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def test_configuration_diagnostic_blocks(self):
        output = "tsconfig.json(1,21): error TS5023: Unknown compiler option.\n"
        self.assertIn("TS5023", self.check_compiler(output, 2, 1))

    def test_global_diagnostic_blocks(self):
        output = "error TS18003: No inputs were found in config file.\n"
        self.assertIn("TS18003", self.check_compiler(output, 2, 1))

    def test_silent_or_abnormal_compiler_failure_blocks(self):
        for status in [1, 2, 7, 139]:
            with self.subTest(status=status):
                self.assertIn(str(status), self.check_compiler("", status, 1))

    def test_unrelated_diagnostic_cannot_hide_fatal_output(self):
        output = (
            "other.ts(1,1): error TS2322: Unrelated source error.\n"
            "FATAL ERROR: compiler could not finish\n"
        )
        self.assertIn("FATAL ERROR", self.check_compiler(output, 1, 1))

    def test_unrelated_localized_multiline_diagnostic_does_not_block(self):
        output = (
            "other.ts(1,1): error TS2322: Typ nie jest przypisywalny.\n"
            "  Typ właściwości jest niezgodny.\n"
        )
        self.assertEqual(self.check_compiler(output, 2, 0), "")

    def test_edited_file_with_spaces_and_parentheses_blocks(self):
        self.source = self.project / "file (copy).ts"
        self.source.touch()
        output = "file (copy).ts(1,1): error TS2322: Edited source error.\n"
        self.assertIn("Edited source", self.check_compiler(output, 2, 1))

    def test_timeout_status_is_preserved(self):
        self.check_compiler("", 124, 124)

    def test_clean_compiler_does_not_block(self):
        self.assertEqual(self.check_compiler("", 0, 0), "")


if __name__ == "__main__":
    unittest.main()
