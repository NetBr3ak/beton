#!/usr/bin/env bash
source "$(dirname "$0")/helpers.sh"

# macOS mktemp doesn't support extensions in templates — use a temp dir.
TMPDIR_TC=$(mktemp -d /tmp/beton_tc_XXXXXX)
trap 'rm -rf "$TMPDIR_TC"' EXIT

# Test: clean Python file exits 0
CLEAN_PY="$TMPDIR_TC/clean.py"
printf 'def greet(name: str) -> str:\n    return f"hello {name}"\n' > "$CLEAN_PY"
bash bin/typecheck-file "$CLEAN_PY" > /dev/null 2>&1
check_eq "$?" "0" "clean python: exits 0"

# Test: Python file with type error exits 1 (if mypy available)
if command -v mypy &>/dev/null; then
  DIRTY_PY="$TMPDIR_TC/dirty.py"
  printf 'def add(x: int) -> int:\n    return x + "oops"\n' > "$DIRTY_PY"
  OUT=$(bash bin/typecheck-file "$DIRTY_PY" 2>&1); STATUS=$?
  check_eq "$STATUS" "1" "type-error python: exits 1"
  check_contains "$OUT" "error" "type-error python: output contains 'error'"
else
  ok "mypy not installed, skip type error test"
  ok "mypy not installed, skip output check"
fi

# Test: TypeScript with type error → exits 1 with real error in output
if command -v tsc &>/dev/null; then
  TS_DIR="$TMPDIR_TC/ts_project"
  mkdir -p "$TS_DIR"
  printf '{"compilerOptions":{"strict":true,"noEmit":true,"target":"ES2020","module":"commonjs"}}' > "$TS_DIR/tsconfig.json"
  printf 'export function add(x: number): number { return x + "oops"; }\n' > "$TS_DIR/bad.ts"
  OUT=$(bash bin/typecheck-file "$TS_DIR/bad.ts" 2>&1); STATUS=$?
  check_eq "$STATUS" "1" "type-error ts: exits 1"
  check_contains "$OUT" "TS2322" "type-error ts: output contains TS2322"
else
  ok "tsc not installed, skip ts type error test"
  ok "tsc not installed, skip ts output check"
fi

# Test: unknown extension exits 0
UNKNOWN="$TMPDIR_TC/file.xyz"
printf 'anything\n' > "$UNKNOWN"
bash bin/typecheck-file "$UNKNOWN" > /dev/null 2>&1
check_eq "$?" "0" "unknown extension: exits 0"

report
