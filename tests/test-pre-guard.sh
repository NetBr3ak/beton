#!/usr/bin/env bash
# Tests for the PreToolUse bypass guard.
# Verifies the guard blocks noqa, type:ignore, ts-ignore, eslint-disable,
# pytest skip markers, jest .skip/.only, ruff: noqa, biome-ignore, prettier-ignore,
# and rm/mv of test files via Bash. Verifies it stays silent on benign edits.
source "$(dirname "$0")/helpers.sh"

GUARD=hooks/pre-tool-guard.sh

# Helper: build a tool event JSON and pipe through the guard, return decision.
guard_decision() {
  local event="$1"
  local out
  out=$(echo "$event" | bash "$GUARD" 2>/dev/null || true)
  if [ -z "$out" ]; then
    echo "allow"
    return
  fi
  echo "$out" | python3 -c "
import json,sys
try:
    print(json.load(sys.stdin).get('decision','allow'))
except Exception:
    print('allow')
" 2>/dev/null || echo "allow"
}

mkevent() {
  # Args: tool, new_string, file_path
  python3 -c "
import json,sys
ev = {
    'tool_name': sys.argv[1],
    'tool_input': {'file_path': sys.argv[3], 'new_string': sys.argv[2]},
    'tool_response': {'output': 'ok'}
}
print(json.dumps(ev))
" "$1" "$2" "$3"
}

mkevent_bash() {
  python3 -c "
import json,sys
print(json.dumps({
    'tool_name': 'Bash',
    'tool_input': {'command': sys.argv[1]},
    'tool_response': {'output': 'ok'}
}))
" "$1"
}

# --- Suppression patterns blocked ---

check_eq "$(guard_decision "$(mkevent Edit 'x = 1  # noqa' /tmp/x.py)")" "block" "noqa: blocked"
check_eq "$(guard_decision "$(mkevent Edit 'x = 1  # noqa: F401' /tmp/x.py)")" "block" "noqa with code: blocked"
check_eq "$(guard_decision "$(mkevent Edit '# ruff: noqa' /tmp/x.py)")" "block" "ruff: noqa block-level: blocked"
check_eq "$(guard_decision "$(mkevent Edit 'x: Any = foo()  # type: ignore' /tmp/x.py)")" "block" "type: ignore: blocked"
check_eq "$(guard_decision "$(mkevent Write '// @ts-ignore' /tmp/x.ts)")" "block" "ts-ignore: blocked"
check_eq "$(guard_decision "$(mkevent Edit '// @ts-expect-error' /tmp/x.ts)")" "block" "ts-expect-error: blocked"
check_eq "$(guard_decision "$(mkevent Edit '// eslint-disable-next-line' /tmp/x.js)")" "block" "eslint-disable-next-line: blocked"
check_eq "$(guard_decision "$(mkevent Edit '/* eslint-disable */' /tmp/x.js)")" "block" "eslint-disable: blocked"
check_eq "$(guard_decision "$(mkevent Edit '// biome-ignore lint: x' /tmp/x.ts)")" "block" "biome-ignore: blocked"
check_eq "$(guard_decision "$(mkevent Edit '// prettier-ignore' /tmp/x.ts)")" "block" "prettier-ignore: blocked"

# --- Test-skip markers blocked ---

check_eq "$(guard_decision "$(mkevent Edit '@pytest.mark.skip' /tmp/test_x.py)")" "block" "pytest.mark.skip: blocked"
check_eq "$(guard_decision "$(mkevent Edit '@pytest.mark.xfail' /tmp/test_x.py)")" "block" "pytest.mark.xfail: blocked"
check_eq "$(guard_decision "$(mkevent Edit '@unittest.skip("flaky")' /tmp/test_x.py)")" "block" "unittest.skip: blocked"
check_eq "$(guard_decision "$(mkevent Edit 'test.skip("flaky", () => {})' /tmp/x.test.ts)")" "block" "test.skip: blocked"
check_eq "$(guard_decision "$(mkevent Edit 'it.only("foo", () => {})' /tmp/x.test.ts)")" "block" "it.only: blocked"

# --- Benign edits pass ---

check_eq "$(guard_decision "$(mkevent Edit 'def f(): return 1' /tmp/x.py)")" "allow" "plain edit: allowed"
check_eq "$(guard_decision "$(mkevent Edit 'const x = 1' /tmp/x.ts)")" "allow" "plain ts edit: allowed"
check_eq "$(guard_decision "$(mkevent Edit '# this is a normal comment about noqa rules' /tmp/x.py)")" "allow" "prose-mention of noqa: allowed"

# --- Bash: rm/mv of test files blocked ---

check_eq "$(guard_decision "$(mkevent_bash 'rm tests/test_auth.py')")" "block" "rm test_auth.py: blocked"
check_eq "$(guard_decision "$(mkevent_bash 'rm foo.test.ts')")" "block" "rm foo.test.ts: blocked"
check_eq "$(guard_decision "$(mkevent_bash 'rm app.spec.js')")" "block" "rm app.spec.js: blocked"
check_eq "$(guard_decision "$(mkevent_bash 'mv test_auth.py test_auth_old.py')")" "block" "mv test_auth.py: blocked"

# --- Bash: benign commands pass ---

check_eq "$(guard_decision "$(mkevent_bash 'ls tests/')")" "allow" "ls tests: allowed"
check_eq "$(guard_decision "$(mkevent_bash 'pytest tests/')")" "allow" "pytest run: allowed"
check_eq "$(guard_decision "$(mkevent_bash 'rm /tmp/scratch.log')")" "allow" "rm of non-test file: allowed"

# --- Opt-out works ---

OUT=$(BETON_BYPASS_GUARD=off bash "$GUARD" <<< "$(mkevent Edit 'x = 1  # noqa' /tmp/x.py)" 2>/dev/null || true)
check_eq "$OUT" "" "BETON_BYPASS_GUARD=off: silent"

# --- Doc-extension carve-out: suppression patterns in non-source files allowed ---
# The verifier never runs lint/typecheck on docs/config files, so a "# noqa"
# in a markdown body has no real-world bypass effect. Don't waste a block.

check_eq "$(guard_decision "$(mkevent Edit 'Use # noqa sparingly.' /tmp/notes.md)")" "allow" "noqa in markdown: allowed"
check_eq "$(guard_decision "$(mkevent Edit '"snippet":"x = 1 # noqa"' /tmp/fixture.json)")" "allow" "noqa in JSON fixture: allowed"
check_eq "$(guard_decision "$(mkevent Edit 'config: "# type: ignore"' /tmp/example.yaml)")" "allow" "type: ignore in YAML: allowed"
check_eq "$(guard_decision "$(mkevent Edit 'when you see @pytest.mark.skip' /tmp/readme.rst)")" "allow" "skip marker in rST: allowed"
check_eq "$(guard_decision "$(mkevent Edit '@pytest.mark.skip' /tmp/x.py)")" "block" "same pattern still blocks in .py"

# Doc-extension allowlist does NOT cover Bash rm/mv against test files;
# extension of the edited file is irrelevant for bash commands.
check_eq "$(guard_decision "$(mkevent_bash 'rm tests/test_auth.py')")" "block" "bash rm test still blocked regardless"

# --- Refusal increments the stats counter ---

# Reset counter, fire a refusal, check it went up.
bin/beton-stats reset >/dev/null 2>&1 || true
BEFORE=$(bin/beton-stats read bypasses_refused 2>/dev/null || echo "0")
guard_decision "$(mkevent Edit 'x = 1  # noqa' /tmp/x.py)" >/dev/null
AFTER=$(bin/beton-stats read bypasses_refused 2>/dev/null || echo "0")
[ "$AFTER" -gt "$BEFORE" ] \
  && ok "refusal increments bypasses_refused (${BEFORE} → ${AFTER})" \
  || not_ok "refusal did not increment counter (before=${BEFORE} after=${AFTER})"

report
