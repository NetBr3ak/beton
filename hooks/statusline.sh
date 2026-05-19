#!/usr/bin/env bash
# BETON statusline. Reads ~/.claude/.beton-state (current verifier outcome)
# and ~/.claude/.beton-stats.json (rolling 24h counters), prints a colored
# badge plus an aggregate counter when something has happened today.
#
# Examples:
#   BETON ✓                                (last edit passed, no activity today)
#   BETON ✓ · 4 blocks                     (last passed, but blocks accumulated)
#   BETON ✗3 · 1 bypass refused            (last edit blocked, plus today's tally)
#
# Exits 0 always; never blocks statusline rendering.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
STATE_FILE="${HOME}/.claude/.beton-state"

[ ! -f "${STATE_FILE}" ] && exit 0

STATUS=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('status', ''))
    print(d.get('errors', 0))
except Exception:
    pass
" "${STATE_FILE}" 2>/dev/null) || exit 0

STATUS_LINE=$(echo "${STATUS}" | head -1)
ERRORS=$(echo "${STATUS}" | tail -1)

SUMMARY=""
if [ -x "${PLUGIN_ROOT}/bin/beton-stats" ]; then
  SUMMARY=$("${PLUGIN_ROOT}/bin/beton-stats" summary 2>/dev/null || true)
fi

case "${STATUS_LINE}" in
  pass)
    printf '\033[32mBETON\033[0m \033[32m✓\033[0m'
    ;;
  block)
    printf '\033[31mBETON\033[0m \033[31m✗%s\033[0m' "${ERRORS}"
    ;;
  *)
    exit 0
    ;;
esac

if [ -n "${SUMMARY}" ]; then
  printf ' \033[2m·\033[0m \033[2m%s\033[0m' "${SUMMARY}"
fi
