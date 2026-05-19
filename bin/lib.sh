#!/usr/bin/env bash
# Shared helpers. Source this file: source "$(dirname "$0")/lib.sh"

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
