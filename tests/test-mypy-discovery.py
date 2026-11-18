"""Mypy discovery must respect section identity, precedence and repository roots."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STRICT = "[mypy]\ndisallow_untyped_defs = True\n"


class MypyDiscoveryTests(unittest.TestCase):
    def check_project(self, files):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for filename, content in files.items():
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            source = root / "project/module.py"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("def value():\n    return 1\n")
            return subprocess.run(
                ["bash", str(ROOT / "bin/typecheck-file"), str(source)],
                cwd=root,
                env=os.environ,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_pyproject_precedes_setup_cfg(self):
        result = self.check_project({
            "project/pyproject.toml": "[tool.mypy]\ndisallow_untyped_defs = true\n",
            "project/setup.cfg": "[mypy]\ndisallow_untyped_defs = False\n",
        })
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no-untyped-def", result.stdout)

    def test_unrelated_sections_do_not_override_the_parent(self):
        for filename, content in {
            "pyproject.toml": "[tool.mypy_plugins]\nenabled = true\n",
            "setup.cfg": "[mypy_extensions]\nenabled = true\n",
        }.items():
            with self.subTest(filename=filename):
                result = self.check_project({
                    "mypy.ini": STRICT,
                    f"project/{filename}": content,
                })
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("no-untyped-def", result.stdout)

    def test_toml_string_is_not_a_configuration_section(self):
        result = self.check_project({
            "mypy.ini": STRICT,
            "project/pyproject.toml": 'description = """\n[tool.mypy]\n"""\n',
        })
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no-untyped-def", result.stdout)

    def test_repository_boundary_stops_parent_configuration(self):
        result = self.check_project({"mypy.ini": STRICT, "project/.git": ""})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
