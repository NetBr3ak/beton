#!/usr/bin/env python3
"""
Pure-Python bypass-pattern evaluator for the PreToolUse guard.

Reads a Claude Code tool event JSON from stdin. If the event contains a
bypass pattern (suppression comment, skip marker, or rm/mv of a test file),
prints a JSON block decision to stdout. Otherwise prints nothing.

Kept separate from the shell hook so the regex set has unit-test coverage
and so bash heredoc/command-substitution interactions can't corrupt it.
"""
from __future__ import annotations

import json
import re
import sys

# (tag, compiled regex). Order matters only for the message: the first
# matching pattern wins, but they're disjoint in practice.
EDIT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ruff-noqa-block", re.compile(r"^\s*#\s*ruff:\s*noqa", re.M)),
    ("noqa", re.compile(r"#\s*noqa(\b|:)", re.I)),
    ("type-ignore", re.compile(r"#\s*type:\s*ignore", re.I)),
    ("ts-ignore", re.compile(r"@ts-(expect-error|ignore|nocheck)\b")),
    ("eslint-disable", re.compile(r"(?://|/\*)\s*eslint-disable(?:-next-line|-line)?\b")),
    ("biome-ignore", re.compile(r"(?://|/\*)\s*biome-ignore\b")),
    ("prettier-ignore", re.compile(r"(?://|/\*)\s*prettier-ignore\b")),
    ("pytest-skip", re.compile(r"@pytest\.mark\.skip\b")),
    ("pytest-xfail", re.compile(r"@pytest\.mark\.xfail\b")),
    ("unittest-skip", re.compile(r"@unittest\.skip\b")),
    ("jest-skip", re.compile(r"\b(it|test|describe)\.skip\s*\(")),
    ("jest-only", re.compile(r"\b(it|test|describe)\.only\s*\(")),
]

# Test-file patterns for rm/mv detection in Bash. Matches:
#   test_<name>.<ext>, <name>_test.<ext>, <name>.test.<ext>, <name>.spec.<ext>
TEST_FILE_RE = re.compile(
    r"\b("
    r"test_[A-Za-z0-9_]+\.(?:py|go|rs)"
    r"|"
    r"[A-Za-z0-9_]+_test\.(?:py|go|rs)"
    r"|"
    r"[A-Za-z0-9_]+\.(?:test|spec)\.(?:ts|tsx|js|jsx|mjs)"
    r")\b"
)

RM_RE = re.compile(r"\brm\b")
MV_RE = re.compile(r"\bmv\b")

# Files where suppression-pattern checks don't apply. The verifier never
# runs lint/typecheck on these, so a suppression-style marker inside a
# markdown document or JSON fixture has no effect on the verifier and
# shouldn't be blocked. Bash rm/mv checks still apply regardless (they
# target test files of any kind).
DOC_EXTENSIONS = frozenset({
    ".md", ".markdown", ".rst", ".txt", ".adoc",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
})

# The regex set above is purely textual, not syntactic. A comment that
# explains the rule, or a string literal that contains the pattern as
# data, will trip the guard. This is intentional: parsing every supported
# language to distinguish real suppressions from prose is more complexity
# than the value justifies, and the cost of a false positive (rewrite the
# line, or set BETON_BYPASS_GUARD=off for the edit) is small compared to
# the cost of a false negative (the entire point of the guard).

EXTRA_CONTEXT_HINT = (
    "Fix the underlying error rather than suppressing it. If the verifier "
    "blocked you, read the specific lint or type error and address that. "
    "If a test is broken, fix the test or the code; do not skip the test."
)


def extract_strings(ti: dict) -> str:
    """Collect new_string / content blobs from Edit/Write/MultiEdit shapes."""
    parts: list[str] = []
    for k in ("new_string", "content"):
        v = ti.get(k)
        if isinstance(v, str):
            parts.append(v)
    edits = ti.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if not isinstance(e, dict):
                continue
            for k in ("new_string", "content"):
                v = e.get(k)
                if isinstance(v, str):
                    parts.append(v)
    return "\n".join(parts)


def find_edit_violation(text: str) -> tuple[str, str] | None:
    for tag, rx in EDIT_PATTERNS:
        m = rx.search(text)
        if m:
            # Build a one-line snippet around the match for the block payload.
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 30)
            snippet = text[start:end].replace("\n", " ").strip()
            return tag, snippet
    return None


def find_bash_violation(command: str) -> tuple[str, str] | None:
    if not command:
        return None
    has_test_target = TEST_FILE_RE.search(command)
    if not has_test_target:
        return None
    if RM_RE.search(command):
        return "rm-test", command.strip()
    if MV_RE.search(command):
        return "mv-test", command.strip()
    return None


def emit_block(tag: str, snippet: str, file_path: str, tool: str) -> None:
    target = file_path or tool or "edit"
    reason = (
        f"BETON BYPASS REFUSED: '{tag}' pattern in {target}. "
        + EXTRA_CONTEXT_HINT
    )
    ctx = f"BETON BYPASS PATTERN: {tag}\nFound: {snippet}"
    print(json.dumps({
        "decision": "block",
        "reason": reason,
        "additionalContext": ctx,
    }))


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        return
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool = event.get("tool_name") or ""
    ti = event.get("tool_input") or {}
    file_path = ti.get("file_path") or ti.get("path") or ""

    if tool in ("Write", "Edit", "MultiEdit"):
        ext = ""
        if isinstance(file_path, str) and "." in file_path:
            ext = "." + file_path.rsplit(".", 1)[-1].lower()
        if ext not in DOC_EXTENSIONS:
            text = extract_strings(ti)
            hit = find_edit_violation(text)
            if hit:
                emit_block(hit[0], hit[1], file_path, tool)
                return

    if tool == "Bash":
        cmd = ti.get("command", "") if isinstance(ti.get("command"), str) else ""
        hit = find_bash_violation(cmd)
        if hit:
            emit_block(hit[0], hit[1], "", tool)
            return


if __name__ == "__main__":
    main()
