"""Regression checks for import-aware Python test selection."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PythonAffectedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project with spaces"
        self.project.mkdir()
        self.write("pyproject.toml", "")

    def write(self, name, content=""):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def selected(self, source):
        result = subprocess.run(
            ["bash", str(ROOT / "bin/run-affected-tests"),
             str(self.project / source), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return {Path(line).relative_to(self.project).as_posix()
                for line in result.stdout.splitlines() if line}

    def test_direct_import_selects_differently_named_test(self):
        self.write("pricing.py", "VALUE = 4\n")
        self.write("tests/test_checkout.py", "from pricing import VALUE\n")
        self.write("tests/test_other.py", "import json\n")
        self.assertEqual(self.selected("pricing.py"), {"tests/test_checkout.py"})

    def test_transitive_imports_and_cycles(self):
        self.write("core.py", "import service\n")
        self.write("service.py", "import core\n")
        self.write("tests/test_workflow.py", "import service\n")
        self.assertEqual(self.selected("core.py"), {"tests/test_workflow.py"})

    def test_src_layout_relative_import_and_package_initialization(self):
        self.write("src/shop/__init__.py")
        self.write("src/shop/pricing.py", "VALUE = 4\n")
        self.write("src/shop/service.py", "from . import pricing\n")
        self.write("tests/test_checkout.py", "from shop.service import checkout\n")
        expected = {"tests/test_checkout.py"}
        self.assertEqual(self.selected("src/shop/pricing.py"), expected)
        self.assertEqual(self.selected("src/shop/__init__.py"), expected)

    def test_conftest_selects_only_its_subtree(self):
        self.write("tests/unit/conftest.py", "VALUE = 1\n")
        self.write("tests/unit/test_checkout.py", "def test_checkout(): pass\n")
        self.write("tests/api/test_other.py", "def test_other(): pass\n")
        self.assertEqual(self.selected("tests/unit/conftest.py"),
                         {"tests/unit/test_checkout.py"})

    def test_filename_matches_stay_selected(self):
        self.write("pricing.py")
        self.write("tests/test_pricing.py", "def test_pricing(): pass\n")
        self.assertEqual(self.selected("pricing.py"), {"tests/test_pricing.py"})

    def test_nested_projects_and_dependencies_are_not_scanned(self):
        self.write("pricing.py")
        self.write("tests/test_checkout.py", "import pricing\n")
        for directory in (".venv", "node_modules", "other-project"):
            self.write(f"{directory}/tests/test_hidden.py", "import pricing\n")
        self.write("other-project/pyproject.toml")
        self.assertEqual(self.selected("pricing.py"), {"tests/test_checkout.py"})

    def test_import_analysis_never_executes_project_code(self):
        marker = self.project / "executed"
        self.write("pricing.py", f"open({str(marker)!r}, 'w').close()\n")
        self.write("tests/test_checkout.py", "import pricing\n")
        self.assertEqual(self.selected("pricing.py"), {"tests/test_checkout.py"})
        self.assertFalse(marker.exists())

    def test_selected_failure_reaches_caller(self):
        self.write("pricing.py")
        self.write("tests/test_checkout.py", "import pricing\n")
        tools = self.project / "tools"
        tools.mkdir()
        runner = tools / "pytest"
        runner.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 7\n')
        runner.chmod(0o755)
        result = subprocess.run(
            ["bash", str(ROOT / "bin/run-affected-tests"),
             str(self.project / "pricing.py")],
            env=dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}"),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 7)
        self.assertIn(str(self.project / "tests/test_checkout.py"), result.stdout)

    def test_test_helper_dependency(self):
        self.write("pricing.py")
        self.write("tests/support.py", "import pricing as subject\n")
        self.write("tests/test_checkout.py", "from support import subject\n")
        self.assertEqual(self.selected("pricing.py"), {"tests/test_checkout.py"})

    def test_unparseable_module_selects_all_tests_conservatively(self):
        self.write("pricing.py")
        self.write("broken.py", "def invalid(\n")
        self.write("tests/test_checkout.py", "import pricing\n")
        self.write("tests/test_other.py", "def test_other(): pass\n")
        self.assertEqual(self.selected("pricing.py"),
                         {"tests/test_checkout.py", "tests/test_other.py"})

    def test_parent_relative_and_wildcard_imports(self):
        self.write("src/shop/__init__.py")
        self.write("src/shop/pricing.py")
        self.write("src/shop/api/__init__.py")
        self.write("src/shop/api/service.py", "from ..pricing import *\n")
        self.write("tests/test_checkout.py", "import shop.api.service as service\n")
        self.assertEqual(self.selected("src/shop/pricing.py"),
                         {"tests/test_checkout.py"})

    def test_changed_fixture_helper_selects_fixture_users(self):
        self.write("pricing.py")
        self.write("tests/unit/conftest.py", "import pricing\n")
        self.write("tests/unit/test_checkout.py", "def test_checkout(): pass\n")
        self.write("tests/api/test_other.py", "def test_other(): pass\n")
        self.assertEqual(self.selected("pricing.py"),
                         {"tests/unit/test_checkout.py"})

    def test_changed_test_runs_itself(self):
        self.write("tests/test_checkout.py", "def test_checkout(): pass\n")
        self.assertEqual(self.selected("tests/test_checkout.py"),
                         {"tests/test_checkout.py"})


if __name__ == "__main__":
    unittest.main()
