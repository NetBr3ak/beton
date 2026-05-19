---
name: beton-swebench
description: Agentless-style bug-fix pipeline. Use when fixing a reported bug, resolving a GitHub issue, reproducing a traceback, or making a failing test pass. Localize, reproduce, fix minimally, validate.
---

# Agentless Bug-Fix Pipeline

For bugs, tracebacks, failing tests in an existing codebase. Structure from the Agentless paper (Xia et al., 2024).

**Phase 1 must complete before Phase 2. Phase 2 must complete before Phase 3. Do not skip or reorder.**

<phase_1_localize>
## 1. Localize

Know where the bug lives before touching any code.

1. Spawn the `localize` subagent with the full issue, error, or stack trace verbatim. Returns up to 5 ranked candidates.
2. Verify the top candidate yourself. Read the suspect function and the lines named in the trace. Do not trust the agent's ranking blindly.
3. Report the location before proceeding:

```
Localized to src/auth.py:42 (validate_token).
Reason: stack frame matches; the `<` on line 47 is the off-by-one.
```

If you cannot localize confidently, stop and ask the user for more context. Do not guess. Guessing is the most common cause of wrong fixes.
</phase_1_localize>

<phase_2_fix>
## 2. Reproduce, then repair

Only after Phase 1 is complete. A failing test is your oracle. Without one you have no way to confirm the fix.

1. Write a reproduction test first. Name it `test_<issue_slug>_regression`. Run it. Confirm it fails before touching production code.
2. Make the minimal change. Touch only the localized function. Do not refactor. Do not add features.
3. The PostToolUse verifier runs after each edit. If it blocks, fix the specific error reported. Do not work around it.
</phase_2_fix>

<phase_3_validate>
## 3. Validate

Only after Phase 2 is complete.

1. Run the reproduction test. Must pass.
2. Run the test suite for the affected directory (`pytest <dir>/ -q`, `bun test <dir>`). Must pass.
3. Report:

```
Fix: src/auth.py:47 (`<` → `<=`)
Reproduction test: PASS
Suite (auth/): PASS (12/12)
```

If the suite regresses, return to Phase 2 with the next-best localization candidate. Do not patch the new failure on top of the old one.
</phase_3_validate>

## Escalation

After 3 failed Phase 3 attempts, stop and ask the user. Either localization keeps missing, or the issue description is incomplete. Sampling without new information rarely converges.
