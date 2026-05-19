#!/usr/bin/env bash
# Shared assertion helpers for BETON tests.
# Source this file in each test script:  source "$(dirname "$0")/helpers.sh"

PASS=0; FAIL=0; TOTAL=0

ok() {
  TOTAL=$((TOTAL+1)); PASS=$((PASS+1))
  printf "  ok %d - %s\n" "$TOTAL" "$1"
}

not_ok() {
  TOTAL=$((TOTAL+1)); FAIL=$((FAIL+1))
  printf "  not ok %d - %s\n" "$TOTAL" "$1"
  [ -n "${2:-}" ] && printf "    # %s\n" "$2"
}

check_eq() {
  local got="$1" expected="$2" label="$3"
  [ "$got" = "$expected" ] \
    && ok "$label" \
    || not_ok "$label" "expected '$expected', got '$got'"
}

check_contains() {
  local haystack="$1" needle="$2" label="$3"
  echo "$haystack" | grep -qF -- "$needle" \
    && ok "$label" \
    || not_ok "$label" "'$needle' not found in output"
}

check_json_key() {
  local json="$1" key="$2" expected="$3" label="$4"
  local got
  got=$(echo "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[2],''))" -- "$key" 2>/dev/null)
  check_eq "$got" "$expected" "$label"
}

report() {
  printf "\n%d tests, %d passed, %d failed\n" "$TOTAL" "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]  # exit 0 if all pass
}
