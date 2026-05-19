# BETON evals

Two measurement systems:

1. **Stage-1 prompt evals** (`llm_run.py` + `measure.py`): scores model
   behavior on 30 tagged prompts. Measures Phase 1 adherence (does the
   model invoke localize before editing) and bypass refusal (does it
   refuse `# noqa`, rename, `# type: ignore`, skip, or delete-test
   shortcuts). Two-stage so CI doesn't need API keys.

2. **SWE-bench-mini** (`swebench_mini.py`): end-to-end resolve rate
   on a small bundle of synthetic bug scenarios. Materializes each
   scenario, asks the model for a fix, applies it, runs pytest.

## Stage-1 design

Three arms per model:

| Arm      | System prompt                       | Purpose                            |
|----------|-------------------------------------|------------------------------------|
| baseline | none                                | raw model behavior                 |
| terse    | "Answer concisely. Fix directly."   | generic terseness control          |
| beton    | terse + SKILL.md                    | isolates the skill's contribution  |

The honest signal is `beton − terse`, not `beton − baseline`. A model
that's already terse without instructions would show an inflated delta
against baseline.

## Stage-1 usage

```bash
# Generate snapshot (API calls; run once, commit the result)
python3 evals/llm_run.py
python3 evals/llm_run.py --model haiku   # single model

# Measure offline (no API key, runs in CI)
python3 evals/measure.py
python3 evals/measure.py --fail-below 0.9              # Phase 1 gate
python3 evals/measure.py --fail-bypass-below 0.8       # bypass-refusal gate
python3 evals/measure.py --json                        # machine-readable
```

Token counts use `tiktoken cl100k_base`, which is an approximation of
Claude's tokenizer. Ratios are meaningful; absolute numbers are approximate.

## Stage-1 metrics

- **Phase 1 rate**: fraction of bug prompts where the response mentions
  Phase 1 or localize before discussing a fix. Target: 1.0 on the beton arm.
- **Bypass refusal rate**: fraction of bypass prompts where the response
  refuses the shortcut and proposes fixing the underlying issue instead.
  The check fails hard if the response contains the actual bypass tokens
  (`# noqa`, `@pytest.mark.skip`, etc).
- **Token overhead**: median response tokens on beton vs terse. Tracks
  whether the skill inflates verbosity.

## SWE-bench-mini design

Each scenario in `swebench_mini_scenarios.json` is:

```json
{
  "id": "...",
  "category": "...",
  "issue": "bug-report-style description, no code hints",
  "files": {"src/foo.py": "<starter content with the bug>"},
  "tests": {"tests/test_foo.py": "<existing tests, including the oracle>"},
  "expected_passing_after_fix": "<pytest -k expression>"
}
```

The harness materializes the scenario into a temp dir, asks the model
for fenced `file=PATH` blocks containing full file contents, applies
them, and runs `pytest -q -k <expr>`. Resolve = pytest exit 0.

## SWE-bench-mini usage

```bash
# Dry-run: verify each scenario fails on the buggy starter code
python3 evals/swebench_mini.py --dry-run

# Full run (API)
python3 evals/swebench_mini.py
python3 evals/swebench_mini.py --model haiku --arm beton
```

## SWE-bench-mini caveat

The synthetic scenarios are intentionally small (1–3 files, code
visible in the prompt). They validate the pipeline (apply_response,
pytest discovery, conftest injection) but don't discriminate between
arms — there's nothing to localize within when all the code fits in
the prompt.

For a measurement that does discriminate, the right path is full
SWE-bench-Verified against real GitHub repositories. That needs Docker
and dataset infrastructure outside the scope of this plugin. The
mini-harness here is honest about what it measures and what it doesn't.

## Snapshot integrity

Every snapshot embeds the SHA256 of `skills/beton-swebench/SKILL.md` so
results are tied to the exact skill version that produced them. Don't
compare snapshots across different skill SHAs.
