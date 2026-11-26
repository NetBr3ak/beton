"""The standalone CLI accepts source paths through project symlinks."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliSymlinkRootTest(unittest.TestCase):
    def test_source_can_use_a_symlinked_project_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "project"
            root.mkdir()
            (root / "pyproject.toml").write_text("")
            (root / "module.py").write_text("value = 1\n")
            test = root / "test_module.py"
            test.write_text("import module\n")
            alias = base / "project_alias"
            alias.symlink_to(root, target_is_directory=True)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

            for arguments in ([], ["--root", str(alias)]):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        [sys.executable, "-m", "beton_checks", "affected", str(alias / "module.py"), "--json", *arguments],
                        text=True, capture_output=True, env=env, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), [str(test)])


if __name__ == "__main__":
    unittest.main()
