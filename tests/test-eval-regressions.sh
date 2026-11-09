#!/usr/bin/env bash
set -eu
python3 -S "$(dirname "$0")/test-eval-regressions.py"
