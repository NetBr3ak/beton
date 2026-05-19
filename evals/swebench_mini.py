#!/usr/bin/env python3
"""
BETON SWE-bench-mini: end-to-end resolve-rate measurement.

The full SWE-bench-Verified dataset requires git checkout of real
repositories and docker-based test harnesses, which is heavyweight for
this plugin. Instead, this harness ships a small bundle of synthetic bug
scenarios that exercise the same skill: localize, write a reproduction
test, make the fix, validate that the test now passes and existing tests
still pass.

Each scenario is a self-contained dict:

    {
        "id":          stable identifier,
        "category":    bug class (off_by_one, null_deref, ...),
        "files":       {relpath: starting_content},
        "tests":       {relpath: existing_test_content},
        "issue":       human-readable bug report,
        "expected_passing_after_fix": list of pytest -k expressions that
                                       should pass once the model fixes the
                                       bug. Used as the validation oracle.
    }

For each scenario and each model, the harness:

  1. Writes the scenario to a temp directory.
  2. Issues a single LLM call with the issue and the file tree. The
     `beton` arm gets the SKILL.md content as the system prompt; the
     `baseline` arm gets nothing.
  3. Parses the model's response for a patch (unified diff or full file
     replacement) and applies it.
  4. Runs `pytest -q -k '<expr>'` against the scenario directory.
  5. Records pass/fail.

The output is `evals/snapshots/swebench-<stamp>.json` with per-scenario
resolve flags and per-model resolve rates.

Usage:
    python3 evals/swebench_mini.py                    # all models
    python3 evals/swebench_mini.py --model haiku      # one model
    python3 evals/swebench_mini.py --dry-run          # validate scenarios only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
SCENARIOS_FILE = Path(__file__).parent / "swebench_mini_scenarios.json"

MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}

MAX_TOKENS = 1500


def load_skill() -> tuple[str, str]:
    path = ROOT / "skills" / "beton-swebench" / "SKILL.md"
    raw = path.read_text()
    if raw.startswith("---"):
        end = raw.index("---", 3)
        raw = raw[end + 3:].lstrip()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return raw, sha


def load_scenarios() -> list[dict]:
    if not SCENARIOS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {SCENARIOS_FILE}. The scenario bundle ships with the plugin; "
            "if you cloned the repo and it's not there, re-fetch from origin."
        )
    return json.loads(SCENARIOS_FILE.read_text())


def write_scenario(scenario: dict, work_dir: Path) -> None:
    """Materialize the scenario's starting state into work_dir."""
    for rel, content in scenario.get("files", {}).items():
        target = work_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    for rel, content in scenario.get("tests", {}).items():
        target = work_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def run_pytest(work_dir: Path, kexpr: str | None = None, timeout: int = 30) -> tuple[bool, str]:
    """Returns (passed, output). passed=True iff exit 0."""
    # Inject conftest.py so `from src.foo import bar` resolves without
    # requiring scenarios to ship __init__.py files.
    conftest = work_dir / "conftest.py"
    if not conftest.exists():
        conftest.write_text(
            "import sys, os\n"
            "sys.path.insert(0, os.path.dirname(__file__))\n"
        )

    cmd = ["pytest", "-q", "--no-header", "--tb=short"]
    if kexpr:
        cmd += ["-k", kexpr]
    try:
        r = subprocess.run(
            cmd, cwd=str(work_dir), capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, "pytest not installed"


def build_prompt(scenario: dict) -> str:
    """Pack scenario files + issue into a single user prompt."""
    parts = [
        "You are fixing a bug in a Python project. Below is the full source tree.",
        "Reply with the FINAL CONTENT of every file you need to change, in fenced",
        "code blocks. Use this exact format:",
        "",
        "```python file=src/foo.py",
        "<full file content here>",
        "```",
        "",
        "Do not output a diff. Output the full file content of each changed file.",
        "Touch as few files as possible. Do not delete or skip tests.",
        "",
        "ISSUE:",
        scenario["issue"],
        "",
        "FILES:",
    ]
    for rel, content in scenario["files"].items():
        parts.append(f"\n```python file={rel}\n{content}```")
    for rel, content in scenario["tests"].items():
        parts.append(f"\n```python file={rel}\n{content}```")
    return "\n".join(parts)


PATCH_RE = re.compile(
    r"```(?:python|py)?\s*file=([^\n`]+)\n(.*?)```",
    re.DOTALL,
)


def apply_response(response: str, work_dir: Path) -> list[str]:
    """Parse fenced `file=PATH` blocks and overwrite those files inside work_dir.

    Paths that try to escape work_dir via `..` segments or absolute paths
    are skipped. A model can return whatever it wants in its response; the
    harness shouldn't let a stray response write to /etc/passwd, the user's
    home, or anywhere outside the temp directory we materialized.
    """
    touched: list[str] = []
    safe_root = work_dir.resolve()
    for m in PATCH_RE.finditer(response):
        rel = m.group(1).strip()
        content = m.group(2)
        candidate = (work_dir / rel).resolve()
        try:
            candidate.relative_to(safe_root)
        except ValueError:
            # Path escapes the work_dir sandbox; ignore the block.
            continue
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(content)
        touched.append(rel)
    return touched


def evaluate_scenario(
    client,
    model_id: str,
    scenario: dict,
    skill_content: str,
    arm: str,
) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"swebench_mini_{scenario['id']}_"))
    try:
        write_scenario(scenario, work)

        # Sanity: existing tests should describe a failure on the buggy code.
        # We run them to see the starting state, but resolve-rate depends only
        # on whether the model's edit makes the expected test pass at the end.

        system = None
        if arm == "beton":
            system = "Answer concisely. Fix issues directly.\n\n" + skill_content

        prompt = build_prompt(scenario)
        kwargs = {
            "model": model_id,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        msg = _call_with_retry(client, **kwargs)
        response = msg.content[0].text if hasattr(msg.content[0], "text") else ""

        touched = apply_response(response, work)
        kexpr = scenario.get("expected_passing_after_fix", "")
        ok, output = run_pytest(work, kexpr=kexpr if kexpr else None)
        return {
            "id": scenario["id"],
            "category": scenario.get("category", "?"),
            "resolved": ok,
            "touched_files": touched,
            "pytest_tail": output[-400:] if output else "",
            "response_tokens": msg.usage.output_tokens,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _call_with_retry(client, **kwargs):
    import anthropic
    for attempt in range(4):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)
    return client.messages.create(**kwargs)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=list(MODELS.keys()), default=None,
                   help="Run a single model rather than all three")
    p.add_argument("--arm", choices=["baseline", "beton", "both"], default="both",
                   help="Which arm(s) to run")
    p.add_argument("--dry-run", action="store_true",
                   help="Materialize scenarios and run pytest on the buggy code only")
    args = p.parse_args()

    scenarios = load_scenarios()
    skill_content, skill_sha = load_skill()

    if args.dry_run:
        # Verify each scenario's pytest expression actually fails on the buggy code.
        for s in scenarios:
            work = Path(tempfile.mkdtemp(prefix=f"swebench_dry_{s['id']}_"))
            try:
                write_scenario(s, work)
                ok, out = run_pytest(work, kexpr=s.get("expected_passing_after_fix") or None)
                status = "FAIL (expected)" if not ok else "PASS (unexpected!)"
                print(f"{s['id']:<20} {status}")
                if ok:
                    print("  scenario does not fail on the buggy code; the fix oracle is wrong")
            finally:
                shutil.rmtree(work, ignore_errors=True)
        return

    try:
        import anthropic
    except ImportError:
        print("anthropic SDK not installed (`pip install anthropic`)", file=sys.stderr)
        raise SystemExit(2)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    models = {args.model: MODELS[args.model]} if args.model else MODELS
    arms = ["baseline", "beton"] if args.arm == "both" else [args.arm]

    results: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "skill_sha256": skill_sha,
        "scenario_count": len(scenarios),
        "models": {},
    }

    for model_key, model_id in models.items():
        print(f"\n=== {model_key} ===", flush=True)
        model_out: dict = {"arms": {}}
        for arm in arms:
            print(f"  {arm}", end="", flush=True)
            arm_results = []
            for s in scenarios:
                r = evaluate_scenario(client, model_id, s, skill_content, arm)
                arm_results.append(r)
                marker = "✓" if r["resolved"] else "✗"
                print(marker, end="", flush=True)
            resolved = sum(1 for r in arm_results if r["resolved"])
            print(f" ({resolved}/{len(arm_results)})")
            model_out["arms"][arm] = {
                "results": arm_results,
                "resolve_rate": round(resolved / len(arm_results), 3) if arm_results else 0,
            }
        results["models"][model_key] = model_out

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_path = SNAPSHOTS_DIR / f"swebench-{stamp}.json"
    canonical = SNAPSHOTS_DIR / "swebench.json"
    out_path.write_text(json.dumps(results, indent=2))
    canonical.write_text(json.dumps(results, indent=2))

    print()
    print("Resolve rates:")
    for model_key, mdata in results["models"].items():
        for arm, adata in mdata["arms"].items():
            print(f"  {model_key:<8} {arm:<10} {adata['resolve_rate']:.0%}")
    print(f"\nSnapshot: {canonical}")


if __name__ == "__main__":
    main()
