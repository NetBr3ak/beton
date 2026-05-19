#!/usr/bin/env bash
# PreToolUse guard for Write|Edit|MultiEdit|Bash.
# Refuses bypass patterns the beton-swebench skill forbids:
#   - suppression comments (noqa, type: ignore, ts-ignore, eslint-disable,
#     biome-ignore, prettier-ignore, ruff: noqa, type: ignore[...])
#   - test skip/only markers (@pytest.mark.skip|xfail, @unittest.skip,
#     it.skip, test.skip, describe.skip, .only on it/test/describe)
#   - rm/mv of test files via Bash
#
# Emits JSON {"decision":"block","reason":..., "additionalContext":...}
# on refusal. Otherwise silent (exit 0).
#
# Opt-out: BETON_BYPASS_GUARD=off
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ "${BETON_BYPASS_GUARD:-on}" = "off" ]; then
  exit 0
fi

EVENT=$(cat 2>/dev/null || true)
[ -z "${EVENT}" ] && exit 0

# Hand the event to the Python evaluator. It prints either nothing (allow)
# or a JSON block decision. We forward whatever it prints.
RESULT=$(printf '%s' "${EVENT}" | python3 "${PLUGIN_ROOT}/hooks/_guard_eval.py" 2>/dev/null || true)

if [ -z "${RESULT}" ]; then
  exit 0
fi

# Refusal increments the bypasses_refused counter, best-effort.
"${PLUGIN_ROOT}/bin/beton-stats" incr bypasses_refused 2>/dev/null || true

printf '%s\n' "${RESULT}"
