"""Baseline tests for the buggy-flask example.

These tests pass against the buggy code. The bug only manifests at the
exact-equals boundary (now == expiry), which no existing test covers.
That's the gap the demo asks the user to fill.

When you run the demo with BETON + Claude Code, ask Claude to:

    "There's an off-by-one in is_token_valid. Add a regression test
     that catches it, then fix the bug."

Phase 1 of the skill (localize) finds it; Phase 2 (write a failing
test) adds the missing assertion; Phase 3 validates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import is_token_valid


def test_token_in_the_future():
    assert is_token_valid(100, 200) is True


def test_token_in_the_past():
    assert is_token_valid(200, 100) is False
