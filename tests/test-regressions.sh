#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tests/test-guard-deletions.py
python3 tests/test-runtime-regressions.py
