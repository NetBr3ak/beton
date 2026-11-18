"""Run mypy with the edited project's settings, not the hook caller's."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MypyConfigurationTests(unittest.TestCase):
    def test_nearest_configuration_is_used_from_another_directory(self):
        configurations = {
            "mypy.ini": "[mypy]\ndisallow_untyped_defs = True\n",
            ".mypy.ini": "[mypy]\ndisallow_untyped_defs = True\n",
            "setup.cfg": "[mypy]\ndisallow_untyped_defs = True\n",
            "pyproject.toml": "[tool.mypy]\ndisallow_untyped_defs = true\n",
        }
        for filename, configuration in configurations.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                project = Path(temp) / "project"
                project.mkdir()
                (project / filename).write_text(configuration)
                source = project / "module.py"
                source.write_text("def value():\n    return 1\n")
                caller = Path(temp) / "caller"
                caller.mkdir()
                result = subprocess.run(
                    ["bash", str(ROOT / "bin/typecheck-file"), str(source)],
                    cwd=caller,
                    env=dict(os.environ, BETON_TC_TIMEOUT="5"),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("no-untyped-def", result.stdout)


if __name__ == "__main__":
    unittest.main()
