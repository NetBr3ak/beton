#!/usr/bin/env bash
# Shared helpers. Source this file: source "$(dirname "$0")/lib.sh"

# beton_mode: resolve BETON_MODE (env var > XDG config file > default).
# Mirrors hooks/beton-config.js. Only "strict" and "off" have real behavior;
# any other or invalid value falls back to "strict".
beton_mode() {
  local mode
  mode=$(printf '%s' "${BETON_MODE:-}" | tr '[:upper:]' '[:lower:]')
  case "$mode" in strict|off) echo "$mode"; return ;; esac

  local cfg="${XDG_CONFIG_HOME:-$HOME/.config}/beton/config.json"
  if [ -f "$cfg" ]; then
    mode=$(python3 -c "
import json
try:
    print(json.load(open('${cfg}')).get('mode', '').lower())
except Exception:
    print('')
" 2>/dev/null)
    case "$mode" in strict|off) echo "$mode"; return ;; esac
  fi

  echo "strict"
}

# _timeout <secs> <cmd> [args...]
# Portable: GNU timeout > gtimeout > perl SIGALRM > no-op fallback.
if command -v timeout &>/dev/null; then
  _timeout() { timeout "$@"; }
elif command -v gtimeout &>/dev/null; then
  _timeout() { gtimeout "$@"; }
elif command -v perl &>/dev/null; then
  _timeout() {
    local secs="$1"; shift
    perl -e '
      my $secs = shift;
      my $pid = fork; die "fork: $!" unless defined $pid;
      if ($pid == 0) { exec @ARGV or die "exec: $!"; }
      local $SIG{ALRM} = sub { kill "TERM", $pid; exit 124; };
      alarm $secs; waitpid($pid, 0); alarm 0; exit ($? >> 8);
    ' -- "$secs" "$@"
  }
else
  _timeout() { shift; "$@"; }
fi
