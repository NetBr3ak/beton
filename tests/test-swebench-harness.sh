#!/usr/bin/env bash
# Unit tests for the SWE-bench-mini harness. Validates:
#   - All scenarios materialize and fail on the buggy starter code
#   - apply_response correctly parses fenced `file=PATH` blocks
#   - A correct hand-written fix applied to scenario 1 makes the test pass
# Does not call the API.
source "$(dirname "$0")/helpers.sh"

# 1. Dry run reports all scenarios as FAIL (expected) — none should accidentally
#    pass on the buggy starter code.
DRY_OUT=$(python3 evals/swebench_mini.py --dry-run 2>&1)
UNEXPECTED=$(echo "${DRY_OUT}" | grep "unexpected" || true)
[ -z "${UNEXPECTED}" ] \
  && ok "dry-run: every scenario fails on buggy code" \
  || not_ok "dry-run: one or more scenarios pass on buggy code: ${UNEXPECTED}"

SCENARIO_COUNT=$(python3 -c "import json; print(len(json.load(open('evals/swebench_mini_scenarios.json'))))")
[ "${SCENARIO_COUNT}" -ge 5 ] \
  && ok "scenario bundle has ${SCENARIO_COUNT} entries (≥5)" \
  || not_ok "scenario bundle too small: ${SCENARIO_COUNT}"

# 2. apply_response: simulate a model that returns a correct fix for the first
#    scenario, apply it to a temp dir, run pytest, verify it passes.
TMPDIR=$(mktemp -d -t beton_swebench_XXXX)
python3 - "${TMPDIR}" << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "evals")
from swebench_mini import apply_response, write_scenario, run_pytest

scenarios = json.load(open("evals/swebench_mini_scenarios.json"))
s = scenarios[0]  # obo-pagination
work = Path(sys.argv[1])
write_scenario(s, work)

# Hand-written correct fix.
patch = '''```python file=src/pagination.py
def page_slice(rows, page, per_page):
    """Return rows for the given 1-indexed page."""
    start = (page - 1) * per_page
    end = start + per_page
    return rows[start:end]
```'''
touched = apply_response(patch, work)
assert "src/pagination.py" in touched, f"expected pagination.py to be touched, got {touched}"

ok, output = run_pytest(work, kexpr=s["expected_passing_after_fix"])
assert ok, f"corrected scenario should pass, but pytest output:\n{output}"
print("PASS")
PYEOF
RES=$?
rm -rf "${TMPDIR}"

[ "${RES}" -eq 0 ] \
  && ok "apply_response: hand-written fix resolves scenario 1" \
  || not_ok "apply_response failed: see python output above"

# 3. apply_response refuses to write outside the work_dir sandbox.
#    A malicious model response shouldn't be able to overwrite /etc/passwd
#    or anywhere else outside the temp dir.
TMPDIR=$(mktemp -d -t beton_swebench_traversal_XXXX)
python3 - "${TMPDIR}" << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, "evals")
from swebench_mini import apply_response

work = Path(sys.argv[1])
malicious = '''```python file=../../../tmp/beton_sandbox_break
breached = True
```
```python file=/tmp/beton_absolute_path_attack
attacked = True
```'''
touched = apply_response(malicious, work)
assert touched == [], f"sandbox break: paths got applied: {touched}"
assert not Path("/tmp/beton_sandbox_break").exists(), "../../../ path escaped sandbox"
assert not Path("/tmp/beton_absolute_path_attack").exists(), "/tmp absolute path escaped sandbox"
print("PASS")
PYEOF
RES=$?
rm -rf "${TMPDIR}" /tmp/beton_sandbox_break /tmp/beton_absolute_path_attack
[ "${RES}" -eq 0 ] \
  && ok "apply_response: rejects path-traversal escapes" \
  || not_ok "apply_response: sandbox escape worked"

report
