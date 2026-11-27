"""Repeated graph discovery reads edits made since the preceding call."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from beton_checks.discovery import affected_tests


class DiscoveryFreshnessTest(unittest.TestCase):
    def test_source_edits_and_new_files_are_seen_between_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").touch()
            a = package / "a.py"
            a.write_text("VALUE = 1\n")
            b = package / "b.py"
            b.write_text("from pkg.a import VALUE\n")
            test = root / "test_b.py"
            test.write_text("from pkg.b import VALUE\n")
            self.assertEqual(affected_tests(a, root), [test])

            c = package / "c.py"
            c.write_text("VALUE = 2\n")
            b.write_text("from pkg.c import VALUE\n")
            self.assertEqual(affected_tests(a, root), [])
            self.assertEqual(affected_tests(c, root), [test])


if __name__ == "__main__":
    unittest.main()
