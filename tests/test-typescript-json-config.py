"""Distinguish JSON source diagnostics from compiler configuration errors."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JsonConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "tsconfig.json").write_text("{}")
        self.source = self.project / "file.ts"
        self.source.write_text("export const value = 1;\n")
        tools = self.project / "tools"
        tools.mkdir()
        compiler = tools / "tsc"
        compiler.write_text(
            '#!/bin/sh\nprintf "%s" "$TSC_OUTPUT"\nexit 2\n'
        )
        compiler.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}")

    def compiler_result(self, path, source_files):
        output = f"{path}(1,1): error TS1136: Property assignment expected.\n"
        for source in source_files:
            full_path = self.project / source
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.touch()
            output += f"{full_path}\n"
        return subprocess.run(
            ["bash", str(ROOT / "bin/typecheck-file"), str(self.source)],
            env=dict(self.env, TSC_OUTPUT=output),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_unrelated_imported_json_does_not_block(self):
        result = self.compiler_result("assets/unrelated.json", ["assets/unrelated.json"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_extended_config_syntax_error_blocks(self):
        result = self.compiler_result("config/base.json", ["file.ts"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("config/base.json", result.stdout)

    def test_primary_config_syntax_error_blocks(self):
        result = self.compiler_result("tsconfig.json", ["file.ts"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("tsconfig.json", result.stdout)

    def test_extended_config_with_nonstandard_extension_blocks(self):
        result = self.compiler_result("config/settings.cfg", ["file.ts"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("config/settings.cfg", result.stdout)

    def test_imported_primary_config_remains_a_configuration_error(self):
        result = self.compiler_result("tsconfig.json", ["tsconfig.json"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
