# buggy-flask

A tiny Flask app with one planted bug. The point is to give you a working surface
to try BETON on without setting up a real project.

## The bug

`is_token_valid(now_ts, expiry_ts)` in `app.py` accepts a token whose expiry is
exactly equal to the current second. It should reject it.

The existing tests in `tests/test_app.py` pass because none of them hit the
equals boundary. That's the gap the demo asks Claude to close.

## Try it without BETON first

```bash
cd examples/buggy-flask
pip install flask pytest
pytest -q
```

Two tests, both green. Now you have a working baseline.

## Then try it with BETON installed

In a Claude Code session, open this directory and ask:

> There's an off-by-one in `is_token_valid`. Tokens that expire at exactly
> "now" are still accepted. Add a regression test that catches it, then fix
> the bug.

The full skill loop should fire:

1. The `localize` subagent narrows in on `app.py` and the comparison operator.
2. Claude writes a new test asserting `is_token_valid(100, 100) is False`.
3. The `PostToolUse` verifier runs the new test on top of the buggy code and
   the test fails. BETON returns the failure verbatim.
4. Claude edits `app.py`, tightening `<=` to `<`.
5. The verifier reruns and the test passes. The statusline flips back to
   `BETON ✓`.

If Claude tries to add `# noqa`, `# type: ignore`, `@pytest.mark.skip`, or to
delete a test, the `PreToolUse` guard blocks the edit before it lands. The
skill text and the hook layer say the same thing.

## What this isn't

This is a demo, not a benchmark. For a measured resolve-rate across the same
kinds of bugs, see `evals/swebench_mini.py`.
