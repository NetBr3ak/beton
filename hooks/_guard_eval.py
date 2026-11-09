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
import functools
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


# Cached: every test of a file asks for the same few candidate paths, and the hook has 5 s.
@functools.cache
def read_head(path: Path, root: Path) -> str | None:
    if not path.is_relative_to(root):
        return None
    result = subprocess.run(
        ["git", "-C", str(path.parent), "show", f"HEAD:./{path.name}"],
        capture_output=True, text=True, timeout=2,
    )
    return result.stdout if result.returncode == 0 else None


def parametrized(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in function.decorator_list:
        if not (isinstance(decorator, ast.Call) and decorator.args
                and ast.unparse(decorator.func).endswith("parametrize")):
            continue
        first = decorator.args[0]
        items = first.elts if isinstance(first, (ast.List, ast.Tuple)) else [first]
        names |= {name.strip() for item in items if isinstance(item, ast.Constant)
                  and isinstance(item.value, str) for name in item.value.split(",")}
    return names


def reached_names(tree: ast.Module, test: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str] | None:
    """Names a test uses directly or through module-level helpers, constants,
    fixtures and its test class. None when the test or a fixture takes a fixture
    defined outside the module (conftest.py, a plugin, pytest itself)."""
    definitions: dict[str, ast.AST] = {}
    owners: dict[ast.AST, ast.ClassDef] = {}
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[statement.name] = statement
        if isinstance(statement, ast.ClassDef):
            owners.update((member, statement) for member in statement.body)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            definitions.update((target.id, statement) for target in ast.walk(statement)
                               if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store))
    pending: list[ast.AST] = [test]
    if owner := owners.get(test):
        pending += [*owner.bases, *owner.decorator_list,
                    *(member for member in owner.body if not getattr(member, "name", "").startswith("test_"))]
    names: set[str] = set()
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node is test or any("fixture" in ast.unparse(d) for d in node.decorator_list)):
            arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            fixtures = {arg.arg for arg in arguments} - {"self", "cls"} - parametrized(node)
            if fixtures - definitions.keys():
                return None
            pending += [definitions[name] for name in fixtures - names]
            names |= fixtures
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id not in names:
                names.add(child.id)
                if child.id in definitions:
                    pending.append(definitions[child.id])
    return names


def import_state(module: str, symbols: set[str] | None, bases: tuple[Path, ...],
                 root: Path, deleted: set[Path]) -> str:
    """'removed', 'retained' or 'external' for one import the tests use.
    symbols is None for a plain `import module`, which only a deleted file satisfies."""
    path = Path(*module.split("."))
    for base in bases:
        for candidate in (base / path.with_suffix(".py"), base / path / "__init__.py"):
            candidate = candidate.resolve()
            if not candidate.is_relative_to(root):
                continue
            current = candidate.read_text() if candidate.is_file() else None
            if candidate in deleted and current is not None:
                return "removed"
            baseline = read_head(candidate, root)
            if current is None and baseline is None:
                continue
            if symbols is None:
                return "retained" if current is not None else "removed"
            old_tree = parse_python(baseline or "")
            if old_tree is None or parse_python(current or "") is None:
                return "retained"
            old_names = {item.name for item in old_tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            bindings = symtable.symtable(current or "", str(candidate), "exec")
            new_names = {symbol.get_name() for symbol in bindings.get_symbols()
                         if symbol.is_assigned() or symbol.is_imported()}
            return "removed" if symbols <= old_names - new_names else "retained"
    # A local package the guard cannot map to a file keeps the test protected.
    return "retained" if any((base / path.parts[0]).exists() for base in bases) else "external"


def used_imports(imports: list[ast.Import | ast.ImportFrom],
                 references: set[str]) -> list[tuple[str, set[str] | None]] | None:
    """(module, symbols) for each import a test uses; symbols is None for `import module`.
    None when the test uses a relative import, which the guard does not resolve."""
    used: list[tuple[str, set[str] | None]] = []
    for node in imports:
        if isinstance(node, ast.Import):
            used += [(alias.name, None) for alias in node.names
                     if (alias.asname or alias.name.split(".")[0]) in references]
            continue
        symbols = {alias.name for alias in node.names if (alias.asname or alias.name) in references}
        if not symbols:
            continue
        if node.level or not node.module:
            return None
        used.append((node.module, symbols))
    return used


def source_removed(test_path: Path, tree: ast.Module, tests: list,
                   root: Path, deleted: set[Path]) -> bool:
    """True when every test reaches removed local source and no retained or unresolved local code."""
    bases = (test_path.parent, root, root / "src")
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    for test in tests:
        references = reached_names(tree, test)
        used = used_imports(imports, references) if references is not None else None
        if used is None:
            return False
        states = {import_state(module, symbols, bases, root, deleted) for module, symbols in used}
        if "retained" in states or "removed" not in states:
            return False
    return True


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
    if removed and not source_removed(path, old_tree, removed, root, set()):
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
        # Bare names only: ./echo can be any script, and rg --pre runs a command on each file.
        shell_syntax = any(char in command for char in ";&|<>$`\n")
        read_only = words[0] in {"echo", "printf", "ls", "cat", "grep", "pytest"}
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
        if not nodes or not source_removed(path, tree, nodes, root, targets):
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
