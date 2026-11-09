"""Regression checks for removing tests only with their source code."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "guard", Path(__file__).resolve().parents[1] / "hooks/_guard_eval.py"
)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)
SOURCE = "def auth():\n    return True\n"
TEST = "from auth import auth\n\ndef test_auth():\n    assert auth()\n"


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "auth.py").write_text(SOURCE)
        (self.root / "test_auth.py").write_text(TEST)

    def decision(self, tool, tool_input):
        event = {"tool_name": tool, "cwd": str(self.root), "tool_input": tool_input}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(output):
            GUARD.main()
        return json.loads(output.getvalue())["decision"] if output.getvalue() else "allow"

    def test_delete_source_and_test_together(self):
        self.assertEqual(self.decision("Bash", {"command": "rm auth.py test_auth.py"}), "allow")

    def test_delete_only_test_is_blocked(self):
        self.assertEqual(self.decision("Bash", {"command": "rm test_auth.py"}), "block")

    def test_unrelated_source_does_not_authorize_deletion(self):
        (self.root / "other.py").write_text("x = 1\n")
        self.assertEqual(self.decision("Bash", {"command": "rm other.py test_auth.py"}), "block")

    def test_rename_test_is_blocked(self):
        self.assertEqual(self.decision("Bash", {"command": "mv test_auth.py old.py"}), "block")

    def test_text_mentioning_rm_is_not_a_deletion(self):
        self.assertEqual(self.decision("Bash", {"command": "echo 'rm test_auth.py'"}), "allow")

    def test_conditional_shell_command_cannot_claim_joint_deletion(self):
        self.assertEqual(self.decision("Bash", {"command": "rm test_auth.py; echo auth.py"}), "block")

    def test_compound_commands_cannot_hide_test_deletion(self):
        for command in ('echo "$(rm test_auth.py)"', 'echo ready && env rm test_auth.py'):
            with self.subTest(command=command):
                self.assertEqual(self.decision("Bash", {"command": command}), "block")

    def test_keep_tests_for_other_source(self):
        (self.root / "other.py").write_text("def other():\n    return True\n")
        with (self.root / "test_auth.py").open("a") as stream:
            stream.write("\nfrom other import other\ndef test_other():\n    assert other()\n")
        self.assertEqual(self.decision("Bash", {"command": "rm auth.py test_auth.py"}), "block")

    def test_function_deletion_and_rename_without_source_change(self):
        for tool, changes in (
            ("Edit", {"old_string": TEST, "new_string": ""}),
            ("Write", {"content": ""}),
            ("MultiEdit", {"edits": [{"old_string": TEST, "new_string": ""}]}),
            ("Edit", {"old_string": "test_auth", "new_string": "check_auth"}),
        ):
            with self.subTest(tool=tool, changes=changes):
                self.assertEqual(self.decision(tool, {"file_path": str(self.root / "test_auth.py"), **changes}), "block")

    def test_function_removal_after_source_removal_in_same_diff(self):
        (self.root / "auth.py").write_text("")
        baseline = {"auth.py": SOURCE}
        with patch.object(GUARD, "read_head", side_effect=lambda path, root: baseline.get(path.name), create=True):
            self.assertEqual(self.decision("Edit", {
                "file_path": str(self.root / "test_auth.py"),
                "old_string": TEST, "new_string": "",
            }), "allow")

    def test_test_without_source_reference_stays_protected(self):
        with (self.root / "test_auth.py").open("a") as stream:
            stream.write("\ndef test_independent():\n    assert False\n")
        self.assertEqual(self.decision("Bash", {"command": "rm auth.py test_auth.py"}), "block")

    def test_conditional_skip_markers_are_blocked(self):
        for marker in ("@pytest.mark.skipif(True)", "@unittest.skipIf(True, 'reason')", "@unittest.skipUnless(False, 'reason')"):
            with self.subTest(marker=marker):
                self.assertEqual(self.decision("Edit", {
                    "file_path": str(self.root / "test_auth.py"), "new_string": marker,
                }), "block")

    def test_callable_assignment_is_not_source_removal(self):
        (self.root / "auth.py").write_text("auth = lambda: True\n")
        with patch.object(GUARD, "read_head", return_value=SOURCE):
            self.assertEqual(self.decision("Write", {
                "file_path": str(self.root / "test_auth.py"), "content": "",
            }), "block")

    def test_symlink_test_cannot_hide_its_name(self):
        (self.root / "test_auth.py").unlink()
        (self.root / "check.py").write_text(TEST)
        (self.root / "test_auth.py").symlink_to(self.root / "check.py")
        self.assertEqual(self.decision("Bash", {"command": "rm test_auth.py"}), "block")

    def test_literal_paths_with_spaces(self):
        (self.root / "folder with spaces").mkdir()
        (self.root / "folder with spaces/auth.py").write_text(SOURCE)
        (self.root / "folder with spaces/test_auth.py").write_text(TEST)
        self.assertEqual(self.decision("Bash", {"command": "rm 'folder with spaces/auth.py' 'folder with spaces/test_auth.py'"}), "allow")


if __name__ == "__main__":
    unittest.main()
