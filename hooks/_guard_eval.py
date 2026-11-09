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

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import symtable
from pathlib import Path

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
    ("pytest-skip", re.compile(r"@pytest\.mark\.skip(?:if)?\b")),
    ("pytest-xfail", re.compile(r"@pytest\.mark\.xfail\b")),
    ("unittest-skip", re.compile(r"@unittest\.skip(?:If|Unless)?\b")),
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


def parse_python(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def test_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tests = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests[node.name] = node
        if isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                    tests[f"{node.name}.{method.name}"] = method
    return tests


def read_head(path: Path, root: Path) -> str | None:
    if not path.is_relative_to(root):
        return None
    result = subprocess.run(
        ["git", "-C", str(path.parent), "show", f"HEAD:./{path.name}"],
        capture_output=True, text=True, timeout=2,
    )
    return result.stdout if result.returncode == 0 else None


def source_removed(test_path: Path, tree: ast.Module, nodes: list,
                   root: Path, deleted: set[Path]) -> bool:
    references = {node.id for test in nodes for node in ast.walk(test) if isinstance(node, ast.Name)}
    local_sources = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
            continue
        symbols = {alias.name for alias in node.names if (alias.asname or alias.name) in references}
        if not symbols:
            continue
        module = Path(*node.module.split("."))
        candidates = [base / module.with_suffix(".py") for base in (test_path.parent, root, root / "src")]
        for candidate in candidates:
            candidate = candidate.resolve()
            if not candidate.is_relative_to(root):
                continue
            before = candidate.read_text() if candidate.is_file() else None
            baseline = None
            if candidate not in deleted:
                baseline = read_head(candidate, root)
            if before is None and baseline is None:
                continue
            local_sources.append(candidate)
            if candidate in deleted:
                break
            old_tree = parse_python(baseline) if baseline is not None else None
            new_tree = parse_python(before or "")
            if old_tree is None or new_tree is None:
                return False
            old_names = {item.name for item in old_tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            bindings = symtable.symtable(before or "", str(candidate), "exec")
            new_names = {symbol.get_name() for symbol in bindings.get_symbols()
                         if symbol.is_assigned() or symbol.is_imported()}
            if not symbols <= old_names - new_names:
                return False
            break
    return bool(local_sources)


def find_test_deletion(ti: dict, root: Path) -> tuple[str, str] | None:
    path = Path(ti.get("file_path") or ti.get("path") or "")
    if not path.is_absolute():
        path = root / path
    if not TEST_FILE_RE.fullmatch(path.name) or path.suffix != ".py" or not path.is_file():
        return None
    before = path.read_text()
    after = before
    if "content" in ti:
        after = ti["content"]
    else:
        for edit in ti.get("edits", [ti]):
            old, new = edit.get("old_string"), edit.get("new_string")
            if isinstance(old, str) and isinstance(new, str) and old:
                after = after.replace(old, new, -1 if edit.get("replace_all") else 1)
    old_tree, new_tree = parse_python(before), parse_python(after)
    if old_tree is None:
        return None
    old_tests = test_functions(old_tree)
    new_tests = test_functions(new_tree) if new_tree else {}
    removed = [node for name, node in old_tests.items() if name not in new_tests]
    if removed and not all(source_removed(path, old_tree, [node], root, set()) for node in removed):
        return "delete-test", str(path)
    return None


def find_bash_violation(command: str, root: Path) -> tuple[str, str] | None:
    if not command or not TEST_FILE_RE.search(command):
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return "shell-test", command.strip()
    if not words:
        return None
    executable = Path(words[0]).name
    if executable == "mv":
        return "mv-test", command.strip()
    if executable != "rm":
        # Compound commands remain textual checks; simple echo/pytest calls do not delete files.
        shell_syntax = any(char in command for char in ";&|<>$`\n")
        read_only = executable in {"echo", "printf", "ls", "cat", "rg", "grep", "pytest"}
        if (shell_syntax or not read_only) and (RM_RE.search(command) or MV_RE.search(command)):
            return "rm-test", command.strip()
        return None
    if any(char in command for char in ";&|<>$`*?\n"):
        return "rm-test", command.strip()
    operands = [root / word for word in words[1:] if not word.startswith("-")]
    targets = {path.resolve() for path in operands}
    tests = [path for path in operands if TEST_FILE_RE.fullmatch(path.name)]
    for path in tests:
        if path.suffix != ".py" or path.is_symlink() or not path.is_file():
            return "rm-test", command.strip()
        tree = parse_python(path.read_text())
        if tree is None:
            return "rm-test", command.strip()
        nodes = list(test_functions(tree).values())
        if not nodes or not all(source_removed(path, tree, [node], root, targets) for node in nodes):
            return "rm-test", command.strip()
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
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
            "additionalContext": ctx,
        },
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

    root = Path(event.get("cwd") or os.getcwd()).resolve()

    if tool in ("Write", "Edit", "MultiEdit"):
        hit = find_test_deletion(ti, root)
        if hit:
            emit_block(hit[0], hit[1], file_path, tool)
            return
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
        hit = find_bash_violation(cmd, root)
        if hit:
            emit_block(hit[0], hit[1], "", tool)
            return


if __name__ == "__main__":
    main()
