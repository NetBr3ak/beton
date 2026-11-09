---
name: beton
description: Reference for the BETON verifier loop. Read this when a tool call is blocked with "BETON VERIFIER ERRORS:" in the additional context.
---

# BETON: Verifier Loop

A `PostToolUse` hook on `Write`, `Edit`, `MultiEdit`. Short-circuit chain:

1. Lint (≤4s)
2. Typecheck (≤5s, only if lint passed)
3. Affected tests (≤8s, only if both passed)

Affected tests are discovered by naming convention: `test_<basename>.<ext>`, `<basename>_test.<ext>`, `<basename>.test.<ext>`, `<basename>.spec.<ext>`.

If everything passes, the hook is silent. If the file extension or language tool is not covered, the hook exits 0 and never blocks on something it cannot check.

## Reading a block payload

```
BETON VERIFIER ERRORS:
LINT:
src/auth.py:3:1: F401 [*] `unused_module` imported but unused
```

```
BETON VERIFIER ERRORS:
TEST:
FAILED tests/test_auth.py::test_token_expiry - AssertionError: expected 401, got 200
```

Steps:
1. Read the error verbatim. Do not guess at the cause.
2. Fix the specific issue named.
3. Re-edit. The hook re-runs.

Do not bypass the verifier. Bypasses include: renaming files, adding `# noqa` / `# type: ignore` suppressions, deleting a test while retaining its source, or moving code to an unchecked path. Fix the root cause. The point is the loop.

## Tuning

If the verifier times out repeatedly, suggest the user raise one of:

- `BETON_VERIFY_TIMEOUT` (legacy test-stage fallback, default 8 seconds)
- `BETON_TC_TIMEOUT` (typecheck, default 5)
- `BETON_TEST_TIMEOUT` (tests, default 8)

## Subagents

- `repo-map`: token-budgeted symbol index. Use before editing unfamiliar code.
- `localize`: ranked candidates from a stack trace or issue. Use at the start of a bug-fix task.

## Companion skill

`beton-swebench` guides localization, reproduction, repair and validation. These are instructions, not proof that a model followed the workflow.
