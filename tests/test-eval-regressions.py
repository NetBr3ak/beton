#!/usr/bin/env python3
import contextlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
measure = importlib.import_module("measure")
swe = importlib.import_module("swebench_mini")

class EvalRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def test_only_scenario_source_is_writable(self):
        scenario = {"files": {"src/a.py": "old\n"}, "tests": {"tests/test_a.py": "oracle\n"}}
        swe.write_scenario(scenario, self.work)
        response = '''```python file=src/a.py
fixed
```
```python file=tests/test_a.py
pass
```
```python file=conftest.py
pass
```
```python file=src/new.py
pass
```'''
        touched = swe.apply_response(response, self.work, scenario["files"])
        self.assertEqual(touched, ["src/a.py"])
        self.assertEqual((self.work / "tests/test_a.py").read_text(), "oracle\n")
        self.assertFalse((self.work / "conftest.py").exists())
        self.assertFalse((self.work / "src/new.py").exists())

    def test_path_traversal_and_symlink_are_rejected(self):
        outside = self.work.parent / "outside.py"
        outside.write_text("original\n")
        self.addCleanup(outside.unlink)
        (self.work / "link.py").symlink_to(outside)
        response = '''```python file=../outside.py
changed
```
```python file=link.py
changed
```'''
        self.assertEqual(swe.apply_response(response, self.work, {"../outside.py", "link.py"}), [])
        self.assertEqual(outside.read_text(), "original\n")

    def test_evaluation_does_not_apply_oracle_edits(self):
        scenario = {"id": "x", "issue": "bug", "files": {"src/a.py": "old\n"},
                    "tests": {"tests/test_a.py": "oracle\n"}}
        response = '''```python file=tests/test_a.py
pass
```
```python file=conftest.py
pass
```'''
        message = SimpleNamespace(content=[SimpleNamespace(text=response)],
                                  usage=SimpleNamespace(output_tokens=1))

        def inspect(work_dir, kexpr=None):
            self.assertEqual((work_dir / "tests/test_a.py").read_text(), "oracle\n")
            self.assertFalse((work_dir / "conftest.py").exists())
            return False, "failed"

        with patch.object(swe, "_call_with_retry", return_value=message), \
                patch.object(swe, "run_pytest", side_effect=inspect):
            result = swe.evaluate_scenario(None, "model", scenario, "", "baseline")
        self.assertFalse(result["resolved"])
        self.assertEqual(result["touched_files"], [])

    def test_dry_run_rejects_pass_and_pytest_errors(self):
        scenario = {"id": "x", "files": {}, "tests": {}}
        for status in (0, 2, 5, -1):
            with self.subTest(status=status), patch.object(swe, "load_scenarios", return_value=[scenario]), \
                    patch.object(swe, "load_skill", return_value=("", "")), \
                    patch.object(swe, "run_pytest_status", return_value=(status, "output")), \
                    patch.object(sys, "argv", ["swebench_mini.py", "--dry-run"]), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    swe.main()
                self.assertNotEqual(exc.exception.code, 0)

    def test_dry_run_rejects_pytest_fixture_errors(self):
        scenario = {"id": "x", "files": {}, "tests": {}}
        with patch.object(swe, "load_scenarios", return_value=[scenario]), \
                patch.object(swe, "load_skill", return_value=("", "")), \
                patch.object(swe, "run_pytest_status", return_value=(1, "1 failed, 1 error")), \
                patch.object(sys, "argv", ["swebench_mini.py", "--dry-run"]), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                swe.main()

    def run_measure(self, snapshot, *args):
        path = self.work / 'snapshot.json'
        path.write_text(json.dumps(snapshot))
        return subprocess.run([sys.executable, "-S", str(ROOT / 'evals/measure.py'), '--snapshot', str(path), *args], capture_output=True, text=True)

    def snapshot(self):
        responses = [{"id": "bug", "kind": "bug", "response": "fix"},
                     {"id": "bypass", "kind": "bypass_noqa", "response": "fix"}]
        return {"prompt_count": 2, "models": {"m": {"arms": {arm: responses for arm in ("baseline", "terse", "beton")}}}}

    def test_json_thresholds_fail_without_corrupting_json(self):
        result = self.run_measure(self.snapshot(), '--json', '--fail-below', '0.9', '--fail-bypass-below', '0.8')
        self.assertNotEqual(result.returncode, 0)
        json.loads(result.stdout)

    def test_empty_and_incomplete_models_fail(self):
        for snapshot in ({"prompt_count": 2, "models": {}},
                         {"prompt_count": 2, "models": {"m": {"arms": {}}}},
                         {"prompt_count": 3, **{k: v for k, v in self.snapshot().items() if k != "prompt_count"}}):
            with self.subTest(snapshot=snapshot):
                self.assertNotEqual(self.run_measure(snapshot, '--json').returncode, 0)

    def test_token_counter_is_labeled(self):
        result = measure.analyze(self.write_snapshot(self.snapshot()))
        self.assertIn(result['token_count_method'], ('tiktoken cl100k_base', 'whitespace words'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            measure.print_report(result)
        self.assertIn(result['token_count_method'], output.getvalue())

    def write_snapshot(self, snapshot):
        path = self.work / 'snapshot.json'
        path.write_text(json.dumps(snapshot))
        return path


if __name__ == '__main__':
    unittest.main()
