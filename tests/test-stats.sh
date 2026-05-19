#!/usr/bin/env bash
# Tests for bin/beton-stats: counter correctness, daily rollover, concurrent
# increments under flock. Catches the race where two parallel hook
# invocations could each load + increment + save and one update would be lost.
source "$(dirname "$0")/helpers.sh"

STATS=bin/beton-stats

# Use a temp HOME so we don't trample the user's actual stats during tests.
export HOME=$(mktemp -d -t beton_stats_test_XXXX)
trap 'rm -rf "$HOME"' EXIT

# --- basic incr/read ---

$STATS reset
check_eq "$($STATS read blocks)" "0" "fresh state: blocks=0"
$STATS incr blocks
check_eq "$($STATS read blocks)" "1" "after one incr: blocks=1"
$STATS incr blocks
$STATS incr blocks
check_eq "$($STATS read blocks)" "3" "after three incrs: blocks=3"

# --- unknown counter is ignored, not stored ---

$STATS incr bogus_counter 2>/dev/null
check_eq "$($STATS read bogus_counter)" "0" "unknown counter: stays 0"
check_eq "$($STATS read blocks)" "3" "unknown counter: doesn't corrupt other counters"

# --- totals accumulate across resets ---

TOTAL_BEFORE=$($STATS read total_blocks)
$STATS reset
$STATS incr blocks
TODAY_AFTER=$($STATS read blocks)
TOTAL_AFTER=$($STATS read total_blocks)
check_eq "$TODAY_AFTER" "1" "after reset+incr: today blocks=1"
[ "$TOTAL_AFTER" -gt "$TOTAL_BEFORE" ] \
  && ok "totals accumulate across resets (${TOTAL_BEFORE} -> ${TOTAL_AFTER})" \
  || not_ok "totals lost across reset (${TOTAL_BEFORE} -> ${TOTAL_AFTER})"

# --- concurrent incr under flock: no lost updates ---

$STATS reset
BEFORE=$($STATS read bypasses_refused)
for i in $(seq 1 50); do $STATS incr bypasses_refused & done
wait
AFTER=$($STATS read bypasses_refused)
GAIN=$((AFTER - BEFORE))
[ "$GAIN" -eq 50 ] \
  && ok "50-way parallel incr: zero loss (gain=${GAIN})" \
  || not_ok "50-way parallel incr lost updates (gain=${GAIN}, expected 50)"

# --- summary output format ---

$STATS reset
SUMMARY=$($STATS summary)
check_eq "$SUMMARY" "" "summary: silent when nothing happened today"

$STATS incr blocks
$STATS incr blocks
$STATS incr bypasses_refused
SUMMARY=$($STATS summary)
echo "$SUMMARY" | grep -qF "2 blocks" \
  && ok "summary: shows block count" \
  || not_ok "summary: missing block count (got: '${SUMMARY}')"
echo "$SUMMARY" | grep -qF "1 bypass refused" \
  && ok "summary: singular 'bypass refused'" \
  || not_ok "summary: bad plural form (got: '${SUMMARY}')"

# --- malformed state file: handled gracefully, not crashed ---

echo "this is not json" > "$HOME/.claude/.beton-stats.json"
$STATS incr blocks 2>/dev/null
check_eq "$($STATS read blocks)" "1" "malformed state recovers via fresh init"

report
