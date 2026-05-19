#!/usr/bin/env bash
# PostToolUse verifier for Write|Edit|MultiEdit.
# Lints, typechecks, runs affected tests. Outputs JSON {"decision":"block",...} on failure.
# Writes state to ~/.claude/.beton-state for statusline display.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
STATE_FILE="${HOME}/.claude/.beton-state"

# shellcheck source=bin/lib.sh
source "${PLUGIN_ROOT}/bin/lib.sh"

# Write state file (best-effort, never block the hook)
_write_state() {
  python3 -c "
import json, sys, os
path = sys.argv[1]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump({'status': sys.argv[2], 'file': sys.argv[3], 'errors': int(sys.argv[4])}, f)
" "${STATE_FILE}" "$1" "${FILE_PATH:-}" "$2" 2>/dev/null || true
}

EVENT=$(cat 2>/dev/null || true)

FILE_PATH=$(echo "${EVENT}" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {}) or {}
    edits = ti.get('edits') or []
    first = edits[0] if edits and isinstance(edits[0], dict) else {}
    print(ti.get('file_path') or ti.get('path') or
          first.get('file_path') or first.get('path') or '')
except Exception:
    print('')
" 2>/dev/null || echo "")

[ -z "${FILE_PATH}" ] || [ ! -f "${FILE_PATH}" ] && exit 0

ERRORS=()
LINT_TIMEOUT="${BETON_LINT_TIMEOUT:-4}"
TC_TIMEOUT="${BETON_TC_TIMEOUT:-5}"
TEST_TIMEOUT="${BETON_TEST_TIMEOUT:-${BETON_VERIFY_TIMEOUT:-8}}"

# Run one verifier stage. Args: label, timeout-seconds, script-path.
# Appends "LABEL:\n<output>" to ERRORS if the script exits non-zero.
_stage() {
  local label="$1" t="$2" script="$3"
  local exit_code=0 out
  out=$(_timeout "$t" bash "${script}" "${FILE_PATH}" 2>&1) || exit_code=$?
  if [ "$exit_code" -ne 0 ] && [ -n "$out" ]; then
    ERRORS+=("${label}:\n${out}")
  fi
}

_stage LINT "${LINT_TIMEOUT}" "${PLUGIN_ROOT}/bin/lint-file"
[ ${#ERRORS[@]} -eq 0 ] && _stage TYPE "${TC_TIMEOUT}" "${PLUGIN_ROOT}/bin/typecheck-file"
if [ ${#ERRORS[@]} -eq 0 ]; then
  # Only run tests inside a real project; in /tmp or random dirs there's nothing
  # meaningful to discover. The sub-script does its own project-root detection,
  # but this gate avoids the walk entirely outside a git tree.
  if git -C "$(dirname "${FILE_PATH}")" rev-parse --show-toplevel &>/dev/null; then
    _stage TEST "${TEST_TIMEOUT}" "${PLUGIN_ROOT}/bin/run-affected-tests"
  fi
fi

if [ "${#ERRORS[@]}" -eq 0 ]; then
  _write_state "pass" "0"
  "${PLUGIN_ROOT}/bin/beton-stats" incr clean 2>/dev/null || true
  exit 0
fi

ERROR_COUNT="${#ERRORS[@]}"
_write_state "block" "${ERROR_COUNT}"
"${PLUGIN_ROOT}/bin/beton-stats" incr blocks 2>/dev/null || true

# Truncation strategy: keep head AND tail. Lint errors are usually at the top
# (file:line:rule), but test assertions and traceback messages land at the
# bottom. Plain head-truncation throws away the load-bearing part of a test
# failure. Default budget 2400 chars; split 1200/1200 with a marker.
RAW=$(printf '%b\n' "${ERRORS[@]}")
BUDGET="${BETON_PAYLOAD_BUDGET:-2400}"
if [ ${#RAW} -le "${BUDGET}" ]; then
  COMBINED="${RAW}"
else
  HALF=$(( BUDGET / 2 ))
  HEAD="${RAW:0:${HALF}}"
  TAIL="${RAW:${#RAW}-${HALF}}"
  HEAD="${HEAD%$'\n'*}"
  TAIL="${TAIL#*$'\n'}"
  COMBINED="${HEAD}"$'\n'"... (middle truncated, total ${#RAW} chars; head+tail kept) ..."$'\n'"${TAIL}"
fi

python3 -c "
import json, sys
print(json.dumps({
    'decision': 'block',
    'reason': sys.argv[1] + ': verifier errors. Fix before proceeding.',
    'additionalContext': 'BETON VERIFIER ERRORS:\n' + sys.argv[2]
}))
" "${FILE_PATH}" "${COMBINED}"
