"""Normal repository symlinks and special files must not break AST discovery."""
import os
import runpy
import subprocess
import tempfile
import tokenize
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIND_AFFECTED = runpy.run_path(str(ROOT / "bin/python-affected-tests"))["affected_tests"]


class PythonFileEntriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        (self.project / "tests").mkdir(parents=True)
        (self.project / "pyproject.toml").touch()
        self.source = self.project / "pricing.py"
        self.source.write_text("VALUE = 1\n")
        self.test = self.project / "tests/test_checkout.py"
        self.test.write_text("import pricing\n")

    def test_missing_optional_workspace_link_does_not_fail_discovery(self):
        (self.project / "optional.py").symlink_to("../optional-workspace/helpers.py")
        result = subprocess.run(
            ["bash", str(ROOT / "bin/run-affected-tests"), str(self.source), "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(self.test)])

    def test_file_link_outside_project_is_not_read(self):
        external = Path(self.temp.name) / "shared.py"
        external.write_text("import pricing\n")
        link = self.project / "tests/test_shared.py"
        link.symlink_to(external)
        open_source = tokenize.open

        def open_local(path):
            self.assertNotEqual(Path(path), link, "AST discovery read an external file link")
            return open_source(path)

        with patch("tokenize.open", side_effect=open_local):
            self.assertEqual(FIND_AFFECTED(self.source, self.project), [self.test])

    def test_link_to_local_module_keeps_target_dependency(self):
        alias = self.project / "local_alias.py"
        alias.symlink_to(self.source.name)
        self.test.write_text("import local_alias\n")
        self.assertEqual(FIND_AFFECTED(self.source, self.project), [self.test])
        self.assertEqual(FIND_AFFECTED(alias, self.project), [self.test])

    def test_link_to_local_test_stays_selected(self):
        alias = self.project / "tests/test_alias.py"
        alias.symlink_to(self.test.name)
        self.assertEqual(FIND_AFFECTED(self.source, self.project), sorted([self.test, alias]))

    def test_fifo_is_not_opened_as_python_source(self):
        stream = self.project / "events.py"
        os.mkfifo(stream)
        open_source = tokenize.open

        def open_regular(path):
            self.assertNotEqual(Path(path), stream, "AST discovery opened a FIFO")
            return open_source(path)

        with patch("tokenize.open", side_effect=open_regular):
            self.assertEqual(FIND_AFFECTED(self.source, self.project), [self.test])

    def test_directory_link_to_optional_workspace_is_not_followed(self):
        (self.project / "optional-tests").symlink_to("../missing", target_is_directory=True)
        self.assertEqual(FIND_AFFECTED(self.source, self.project), [self.test])


if __name__ == "__main__":
    unittest.main()
