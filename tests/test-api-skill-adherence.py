#!/usr/bin/env python3
"""
Live API test: skill adherence across Sonnet 4.6, Opus 4.7, Haiku 4.5.
Tests that models follow the beton-swebench Phase 1 directive.

Usage: python3 tests/test-api-skill-adherence.py
Cost: ~$0.02-0.05 per run (3 models × 3 prompts each).
"""
import os
import sys
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODELS = [
    ("claude-haiku-4-5-20251001",  "Haiku 4.5"),
    ("claude-sonnet-4-6",          "Sonnet 4.6"),
    ("claude-opus-4-7",            "Opus 4.7"),
]

def load_skill(path: str) -> str:
    with open(path) as f:
        content = f.read()
    # Strip YAML frontmatter
    if content.startswith("---"):
        end = content.index("---", 3)
        content = content[end + 3:].lstrip()
    return content

SKILL = load_skill("skills/beton-swebench/SKILL.md")

SYSTEM = f"""You are Claude Code, an AI coding assistant.
The following skill is active and must be followed exactly:

{SKILL}"""

# (prompt, expected_signal, description)
TEST_CASES = [
    (
        "Fix this bug: AttributeError: 'NoneType' object has no attribute 'split' "
        "at line 47 in src/parser.py",
        ["phase 1", "localize", "phase_1"],
        "explicit traceback → Phase 1 localize required",
    ),
    (
        "Our API returns 500 errors in production. Please fix it.",
        ["phase 1", "localize", "ask", "more context", "cannot localize"],
        "vague issue → should ask for more context",
    ),
    (
        "test_token_expiry is failing with: AssertionError: expected 401, got 200",
        ["phase 1", "localize", "phase_1"],
        "failing test → Phase 1 before editing",
    ),
]

PASS, FAIL = 0, 0

def check(response_text: str, signals: list[str]) -> bool:
    text = response_text.lower()
    return any(s.lower() in text for s in signals)

print("=" * 60)
print("BETON skill adherence — live API test")
print("=" * 60)

for model_id, model_name in MODELS:
    print(f"\n--- {model_name} ({model_id}) ---")

    for prompt, signals, desc in TEST_CASES:
        kwargs: dict = dict(
            model=model_id,
            max_tokens=512,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        # Haiku 4.5: no betas needed, just standard call
        # Sonnet 4.6: adaptive thinking active by default at high effort
        # Opus 4.7: standard call

        try:
            resp = client.messages.create(**kwargs)
            text = resp.content[0].text
            passed = check(text, signals)
            status = "PASS" if passed else "FAIL"
            PASS += passed
            FAIL += (1 - passed)
            snippet = text[:120].replace("\n", " ")
            print(f"  [{status}] {desc}")
            if not passed:
                print(f"         signals wanted: {signals}")
                print(f"         got: {snippet!r}")
            else:
                print(f"         → {snippet!r}")
        except anthropic.APIError as e:
            FAIL += 1
            print(f"  [ERR ] {desc}: {e}")

total = PASS + FAIL
print(f"\n{'=' * 60}")
print(f"Results: {PASS}/{total} passed")
if FAIL:
    print("FAIL — skill adherence regressions detected")
    sys.exit(1)
else:
    print("OK — all models follow skill directives")
