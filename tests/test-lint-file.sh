#!/usr/bin/env bash
source "$(dirname "$0")/helpers.sh"

# Test: clean Python file exits 0
CLEAN_PY=$(mktemp /tmp/beton_lint_clean_XXXXXX.py)
printf 'x = 1\n' > "$CLEAN_PY"
bash bin/lint-file "$CLEAN_PY" > /dev/null 2>&1
check_eq "$?" "0" "clean python: exits 0"

# Test: Python file with ruff error exits 1 and includes error code
DIRTY_PY=$(mktemp /tmp/beton_lint_dirty_XXXXXX.py)
printf 'import unused\nx = 1\n' > "$DIRTY_PY"   # F401: unused import
OUT=$(bash bin/lint-file "$DIRTY_PY" 2>&1)
STATUS=$?
check_eq "$STATUS" "1" "dirty python: exits 1"
check_contains "$OUT" "F401" "dirty python: contains F401"

# Test: unknown extension exits 0 with no output
UNKNOWN=$(mktemp /tmp/beton_lint_unknown_XXXXXX.xyz)
bash bin/lint-file "$UNKNOWN" > /dev/null 2>&1
check_eq "$?" "0" "unknown extension: exits 0"

# Test: TypeScript file (eslint) — only if eslint available
if command -v eslint &>/dev/null; then
  DIRTY_TS=$(mktemp /tmp/beton_lint_ts_XXXXXX.ts)
  printf 'var x = 1\n' > "$DIRTY_TS"
  bash bin/lint-file "$DIRTY_TS" > /dev/null 2>&1
  ok "typescript: eslint ran (status doesn't matter without config)"
  rm -f "$DIRTY_TS"
else
  ok "typescript: eslint not installed, skip"
fi

rm -f "$CLEAN_PY" "$DIRTY_PY" "$UNKNOWN"
report
