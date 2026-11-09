"""Executable regression checks for verifier errors and project paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.root / "home"), BETON_MODE="strict")
        self.bin = self.root / "tools"
        self.bin.mkdir()
        self.env["PATH"] = f"{self.bin}:{os.environ['PATH']}"

    def tool(self, name, content):
        target = self.bin / name
        target.write_text("#!/usr/bin/env bash\n" + content)
        target.chmod(0o755)

    def run_script(self, name, file):
        return subprocess.run(["bash", str(ROOT / "bin" / name), str(file)],
                              env=self.env, capture_output=True, text=True)

    def test_config_path_with_apostrophe(self):
        config = self.root / "user's config"
        (config / "beton").mkdir(parents=True)
        (config / "beton/config.json").write_text('{"mode":"off"}')
        self.env.pop("BETON_MODE")
        self.env["XDG_CONFIG_HOME"] = str(config)
        result = subprocess.run(["bash", "-c", 'source "$1"; beton_mode', "bash", str(ROOT / "bin/lib.sh")],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "off")

    def test_silent_stage_failure_blocks(self):
        plugin = self.root / "plugin with spaces"
        (plugin / "bin").mkdir(parents=True)
        shutil.copy(ROOT / "bin/lib.sh", plugin / "bin/lib.sh")
        for script, code in (("lint-file", 7), ("typecheck-file", 0)):
            (plugin / "bin" / script).write_text(f"exit {code}\n")
        source = self.root / "file.py"
        source.write_text("x = 1\n")
        self.env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
        event = {"tool_input": {"file_path": str(source)}}
        result = subprocess.run(["bash", str(ROOT / "hooks/post-tool-verify.sh")], input=json.dumps(event),
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertIn("7", result.stdout)

    def test_eslint_fatal_error_propagates(self):
        self.tool("eslint", "echo 'invalid config' >&2\nexit 2\n")
        (self.root / "eslint.config.js").write_text("export default [;\n")
        source = self.root / "file.ts"
        source.touch()
        result = self.run_script("lint-file", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid config", result.stdout + result.stderr)

    def test_project_without_eslint_config_skips_eslint(self):
        self.tool("eslint", "echo 'no eslint.config file' >&2\nexit 2\n")
        source = self.root / "dir with spaces/file.js"
        source.parent.mkdir()
        source.touch()
        result = self.run_script("lint-file", source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tsc_dependency_error_propagates(self):
        self.tool("tsc", "echo 'dependency.ts(1,1): error TS2322'\nexit 2\n")
        (self.root / "tsconfig.json").write_text("{}")
        source = self.root / "file.ts"
        source.touch()
        result = self.run_script("typecheck-file", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency.ts", result.stdout)

    def test_edited_test_runs_from_project_with_spaces(self):
        project = self.root / "project with spaces"
        (project / "tests").mkdir(parents=True)
        (project / "pyproject.toml").touch()
        source = project / "tests/test_auth.py"
        source.write_text("def test_auth():\n    assert False\n")
        self.tool("pytest", 'printf "%s\\n" "$PWD" "$@"\nexit 1\n')
        result = self.run_script("run-affected-tests", source)
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(project), result.stdout.splitlines())
        self.assertIn(str(source), result.stdout.splitlines())

    def test_repo_map_reads_ctags_output(self):
        self.tool("ctags", 'if [ "$1" = "--version" ]; then echo "Universal Ctags"; else echo \'{"_type":"tag","path":"auth.py","name":"auth","kind":"function","line":1}\'; fi\n')
        result = subprocess.run(["bash", str(ROOT / "bin/repo-map"), str(self.root)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("auth :1", result.stdout)

    def test_repo_map_short_budget_is_not_a_pipe_failure(self):
        self.tool("ctags", 'if [ "$1" = "--version" ]; then echo "Universal Ctags"; else for n in {1..100}; do echo \'{"_type":"tag","path":"auth.py","name":"auth","kind":"function","line":1}\'; done; fi\n')
        result = subprocess.run(["bash", str(ROOT / "bin/repo-map"), str(self.root), "--budget", "1"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout), 4)

    def test_guard_evaluator_failure_denies(self):
        plugin = self.root / "broken plugin"
        (plugin / "bin").mkdir(parents=True)
        shutil.copy(ROOT / "bin/lib.sh", plugin / "bin/lib.sh")
        self.env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
        result = subprocess.run(["bash", str(ROOT / "hooks/pre-tool-guard.sh")], input='{"tool_name":"Edit"}',
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("BETON", result.stderr)


if __name__ == "__main__":
    unittest.main()
