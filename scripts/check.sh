#!/usr/bin/env bash
# Offline repository gate. State must not touch the caller's Claude settings.
set -euo pipefail
cd "$(dirname "$0")/.."

CHECK_HOME=$(mktemp -d "${TMPDIR:-/tmp}/beton-check.XXXXXX")
trap 'rm -rf "$CHECK_HOME"' EXIT
export HOME="$CHECK_HOME"
export BETON_MODE=strict
export BETON_BYPASS_GUARD=on
export PYTHONDONTWRITEBYTECODE=1

for tool in python3 node ruff mypy pytest; do
  command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done
python3 -c 'import yaml'

for file in hooks/*.sh bin/lib.sh bin/lint-file bin/typecheck-file bin/run-affected-tests bin/repo-map tests/*.sh scripts/*.sh; do
  bash -n "$file"
done
for file in hooks/*.js; do
  node --check "$file"
done
ruff check hooks/_guard_eval.py evals/ bin/beton-stats bin/beton-session-stats tests/test-guard-deletions.py tests/test-runtime-regressions.py tests/test-eval-regressions.py
mypy --follow-imports=silent hooks/_guard_eval.py

failed=0
for test_file in tests/test-*.sh; do
  echo "=== $test_file ==="
  # The legacy harness shadows and deletes an exported TMPDIR between cases.
  if [ "$test_file" = tests/test-swebench-harness.sh ]; then
    env -u TMPDIR bash "$test_file" || failed=1
  else
    bash "$test_file" || failed=1
  fi
done
exit "$failed"
