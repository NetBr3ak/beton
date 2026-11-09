# BETON evals

This directory contains optional API experiments and an offline scenario check. No model-response snapshots are bundled. The repository makes no measured claim about model quality.

## Prompt experiment

`llm_run.py` sends the prompts in `prompts/en.json` to the configured models. It records responses for three arms:

| Arm | System prompt |
|---|---|
| baseline | None |
| terse | Short instructions to fix directly |
| beton | The terse instructions plus `beton-swebench/SKILL.md` |

Install the optional `anthropic` SDK in a separate virtual environment before an API run. Supply `ANTHROPIC_API_KEY` through your environment, never a tracked file. Calls incur provider charges. Model identifiers in the scripts are examples; check availability in your account before running.

```bash
python3 -m pip install anthropic
python3 evals/llm_run.py --model haiku
```

The script writes a timestamped snapshot under `evals/snapshots/`. Pass that exact file to the offline analyzer; the default `results.json` is not bundled:

```bash
python3 evals/measure.py --snapshot evals/snapshots/RESULT_FILE.json
python3 evals/measure.py --snapshot evals/snapshots/RESULT_FILE.json --json
```

`--fail-below` sets the minimum Phase 1 signal rate. `--fail-bypass-below` sets the minimum bypass-refusal signal rate. Both apply to text and JSON output. A snapshot must have nonempty models, all declared arms and matching prompt IDs and counts.

These metrics are text heuristics:

- Phase 1 detects a mention of `localize`, `phase 1` or `phase_1`. It does not observe tool execution or establish the order of actions.
- Bypass refusal detects refusal phrases and rejects responses containing selected bypass strings. Quoting a forbidden string can count as a failure even in a refusal.
- Response length counts whitespace-separated words. Historical JSON field names contain `tokens`, but the method label is `whitespace words`. These are not provider token counts.

Compare `beton` with `terse` on the same prompts to separate the skill from generic instructions to be concise. Snapshots record the skill-file hash. Do not treat results from different skill hashes as the same experiment.

CI tests the analyzer using synthetic fixtures. It does not publish API results or run a default snapshot.

## Synthetic bug scenarios

`swebench_mini_scenarios.json` contains starter source and oracle tests for planted bugs. These are synthetic scenarios, not SWE-bench-Verified data. A scenario names its source files, test files and the pytest expression that selects its oracle.

Check the starter bugs without an API key:

```bash
python3 -m pip install pytest
python3 evals/swebench_mini.py --dry-run
```

Each scenario must produce a pytest assertion failure on the buggy starter code. A passing scenario, collection error, missing pytest or timeout makes the command fail. The number of scenarios is the length of the JSON array, not a model-performance result.

An optional API run asks for full-file replacements, applies only listed source files and runs the oracle tests:

```bash
python3 evals/swebench_mini.py --model haiku --arm beton
```

Oracle tests, the root `conftest.py`, new files and paths outside the work directory are excluded from model replacements. This preserves the oracle, but it does not sandbox Python execution. Run model-generated code in a disposable isolated environment without host credentials or private files.

The starter source is visible in each prompt. These small scenarios check the harness; they do not measure repository-scale localization. See [SECURITY.md](../SECURITY.md) for the execution boundary.
