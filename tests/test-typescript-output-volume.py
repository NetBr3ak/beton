"""Compiler file listings must not reach verifier failure messages."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("BETON_VERIFY_ROOT", Path(__file__).resolve().parents[1]))


class CompilerOutputVolumeTests(unittest.TestCase):
    def test_file_listing_is_silent_on_success_and_removed_from_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "file.ts"
            source.touch()
            (project / "tsconfig.json").write_text("{}")
            tools = project / "tools"
            tools.mkdir()
            compiler = tools / "tsc"
            compiler.write_text(
                '#!/bin/sh\nprintf "%s" "$TSC_OUTPUT"\nexit "$TSC_STATUS"\n'
            )
            compiler.chmod(0o755)
            listing = f"{source}\n" * 1000
            for status in [0, 1, 139, 124]:
                with self.subTest(status=status):
                    failure = "FATAL ERROR: compiler did not finish\n" if status else ""
                    result = subprocess.run(
                        ["bash", str(ROOT / "bin/typecheck-file"), str(source)],
                        env=dict(
                            os.environ,
                            PATH=f"{tools}:{os.environ['PATH']}",
                            TSC_OUTPUT=listing + failure,
                            TSC_STATUS=str(status),
                        ),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    expected = 124 if status == 124 else int(status != 0)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertNotIn(str(source), result.stdout)
                    if status:
                        self.assertIn("FATAL ERROR", result.stdout)
                    else:
                        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
