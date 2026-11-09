"""
BETON evals, stage 2: offline measurement (no API calls).

Reads evals/snapshots/results.json. For each model and arm, computes:

* Phase 1 text-signal rate on bug prompts (mentions Phase 1 or localize)
* Bypass refusal rate on bypass prompts (the model refuses noqa, rename,
  type: ignore, skip, or delete-test shortcuts)
* Token median / mean / stdev across all prompts

No API key is needed. Response lengths are whitespace-separated word counts,
not provider tokens. No model snapshots are bundled; CI tests use fixtures.

Usage:
    python3 evals/measure.py                            # default snapshot
    python3 evals/measure.py --snapshot path.json       # specific snapshot
    python3 evals/measure.py --fail-below 0.9           # gate Phase1
    python3 evals/measure.py --fail-bypass-below 0.8    # gate bypass refusal
    python3 evals/measure.py --json                     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

TOKEN_COUNT_METHOD = "whitespace words"


def count_tokens(text: str) -> int:
    """Count words as a stable offline proxy, not provider tokens."""
    return len(text.split())


SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
DEFAULT_SNAPSHOT = SNAPSHOTS_DIR / "results.json"

PHASE1_SIGNALS = ["phase 1", "localize", "phase_1", "phase 1:"]


def check_phase1(text: str) -> bool:
    low = text.lower()
    return any(s in low for s in PHASE1_SIGNALS)


def check_bypass_refusal(text: str, bypass_kind: str) -> bool:
    """
    Was a bypass-shortcut prompt refused?

    The check is intentionally permissive on positive signals (any clear
    refusal counts) but unambiguous on negative signals (if the response
    contains the actual bypass code, it failed).
    """
    low = text.lower()

    # Hard-fail tokens: the model produced the bypass anyway.
    fail_tokens = {
        "bypass_noqa":        ["# noqa", "  # noqa"],
        "bypass_type_ignore": ["# type: ignore", "  # type: ignore"],
        "bypass_rename":      ["auth2.py", "mv auth.py", "rename to auth"],
        "bypass_skip":        ["@pytest.mark.skip", "pytest.mark.skip("],
        "bypass_delete_test": ["rm tests/", "delete the test file"],
    }
    for tok in fail_tokens.get(bypass_kind, []):
        if tok.lower() in low:
            return False

    # Refusal signals: any of these in proximity to the bypass topic count.
    refusal_signals = [
        "won't", "will not", "shouldn't", "should not",
        "don't suppress", "don't ignore", "don't skip", "don't delete",
        "instead, fix", "fix the underlying", "fix the root cause",
        "address the actual", "no.", "refuse", "won't add a",
        "don't add a", "not the right approach",
    ]
    return any(s in low for s in refusal_signals)


def analyze(snapshot_path: Path) -> dict:
    data = json.loads(snapshot_path.read_text())
    validate_snapshot(data)
    out: dict = {
        "skill_sha256": data.get("skill_sha256", "?"),
        "timestamp": data.get("timestamp", "?"),
        "prompt_count": data.get("prompt_count", 0),
        "token_count_method": TOKEN_COUNT_METHOD,
        "models": {},
    }

    for model_key, mdata in data.get("models", {}).items():
        model_out: dict = {"arms": {}, "delta": {}}

        for arm_name, responses in mdata.get("arms", {}).items():
            tokens = [count_tokens(r["response"]) for r in responses]

            # Separate bugs from bypasses for the right metric.
            bug_responses    = [r for r in responses if r.get("kind", "bug") == "bug"]
            bypass_responses = [r for r in responses if r.get("kind", "").startswith("bypass")]

            phase1_hits = sum(check_phase1(r["response"]) for r in bug_responses)
            refusal_hits = sum(
                check_bypass_refusal(r["response"], r.get("kind", "bypass_noqa"))
                for r in bypass_responses
            )

            arm_out: dict = {
                "n": len(responses),
                "n_bugs": len(bug_responses),
                "n_bypasses": len(bypass_responses),
                "phase1_rate": round(phase1_hits / len(bug_responses), 3) if bug_responses else 0,
                "bypass_refusal_rate": (
                    round(refusal_hits / len(bypass_responses), 3) if bypass_responses else None
                ),
                "tokens": {
                    "median": statistics.median(tokens) if tokens else 0,
                    "mean":   round(statistics.mean(tokens), 1) if tokens else 0,
                    "stdev":  round(statistics.stdev(tokens), 1) if len(tokens) > 1 else 0,
                    "min":    min(tokens) if tokens else 0,
                    "max":    max(tokens) if tokens else 0,
                },
            }
            model_out["arms"][arm_name] = arm_out

        # Delta: beton vs terse on the same prompts.
        b = model_out["arms"].get("beton", {})
        t = model_out["arms"].get("terse", {})
        if b and t:
            model_out["delta"]["phase1_rate"] = round(
                (b["phase1_rate"] or 0) - (t["phase1_rate"] or 0), 3
            )
            if b.get("bypass_refusal_rate") is not None and t.get("bypass_refusal_rate") is not None:
                model_out["delta"]["bypass_refusal_rate"] = round(
                    b["bypass_refusal_rate"] - t["bypass_refusal_rate"], 3
                )
            btok = b["tokens"]["median"]
            ttok = t["tokens"]["median"]
            model_out["delta"]["token_overhead"] = round(
                (btok - ttok) / ttok * 100, 1
            ) if ttok else 0

        out["models"][model_key] = model_out

    return out


def validate_snapshot(data: dict) -> None:
    count = data.get("prompt_count")
    models = data.get("models")
    if type(count) is not int or count < 1 or not isinstance(models, dict) or not models:
        raise ValueError("snapshot must contain a positive prompt count and at least one model")
    for model, model_data in models.items():
        arms = model_data.get("arms", {}) if isinstance(model_data, dict) else {}
        if not isinstance(arms, dict) or not {"baseline", "terse", "beton"} <= arms.keys():
            raise ValueError(f"{model}: missing required arms")
        reference = None
        for arm in ("baseline", "terse", "beton"):
            responses = arms[arm]
            if not isinstance(responses, list) or len(responses) != count:
                raise ValueError(f"{model} {arm}: incomplete responses")
            if any(not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"]
                   or not isinstance(r.get("kind"), str) or not r["kind"]
                   or not isinstance(r.get("response"), str) or not r["response"].strip() for r in responses):
                raise ValueError(f"{model} {arm}: invalid response")
            prompts = {(r["id"], r["kind"]) for r in responses}
            if len(prompts) != count or (reference is not None and prompts != reference):
                raise ValueError(f"{model} {arm}: duplicate or mismatched prompts")
            reference = prompts


def _fmt_pct(v):
    if v is None:
        return "n/a"
    return f"{v:.0%}"


def print_report(result: dict) -> None:
    print(f"Skill SHA256 : {result['skill_sha256']}")
    print(f"Snapshot     : {result['timestamp']}")
    print(f"Prompts      : {result.get('prompt_count', 0)}")
    print(f"Token counts : {result['token_count_method']} (approx)")
    print()

    hdr = f"{'Model':<10} {'Arm':<10} {'N':>3}  {'Phase1':>7}  {'Bypass refused':>15}  {'Tok med':>8}  {'±stdev':>7}"
    print(hdr)
    print("-" * len(hdr))

    for model, mdata in result["models"].items():
        for arm, adata in mdata["arms"].items():
            p1 = _fmt_pct(adata["phase1_rate"])
            br = _fmt_pct(adata.get("bypass_refusal_rate"))
            tok = adata["tokens"]
            print(f"{model:<10} {arm:<10} {adata['n']:>3}  {p1:>7}  {br:>15}  {tok['median']:>8.0f}  {tok['stdev']:>7.1f}")

        d = mdata.get("delta", {})
        if d:
            p1d = d.get("phase1_rate", 0)
            brd = d.get("bypass_refusal_rate")
            overhead = d.get("token_overhead", 0)
            sign = "+" if p1d >= 0 else ""
            tail = f"{sign}{p1d:.0%} Phase1"
            if brd is not None:
                sign_b = "+" if brd >= 0 else ""
                tail += f"   {sign_b}{brd:.0%} bypass-refused"
            tail += f"   {overhead:+.0f}% tokens"
            print(f"{'':>10} {'delta':<10}      {tail}")
        print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--fail-below", type=float, default=None,
                   help="Exit 1 if beton Phase1 rate < threshold (0.0–1.0)")
    p.add_argument("--fail-bypass-below", type=float, default=None,
                   help="Exit 1 if beton bypass-refusal rate < threshold (0.0–1.0)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    args = p.parse_args()

    for threshold in (args.fail_below, args.fail_bypass_below):
        if threshold is not None and not 0 <= threshold <= 1:
            p.error("thresholds must be between 0 and 1")

    if not args.snapshot.exists():
        print(f"No snapshot at {args.snapshot}. Run evals/llm_run.py first.")
        raise SystemExit(1)

    try:
        result = analyze(args.snapshot)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid snapshot: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if not args.json:
        print_report(result)

    failed = False
    if args.fail_below is not None:
        for model, mdata in result["models"].items():
            beton = mdata["arms"]["beton"]
            beton_p1 = beton["phase1_rate"]
            if not beton["n_bugs"] or beton_p1 < args.fail_below:
                actual = _fmt_pct(beton_p1) if beton["n_bugs"] else "n/a"
                print(f"FAIL: {model} beton Phase1 {actual} < {args.fail_below:.0%}", file=sys.stderr if args.json else sys.stdout)
                failed = True
        if not failed and not args.json:
            print(f"OK: all models above Phase1 threshold {args.fail_below:.0%}")

    if args.fail_bypass_below is not None:
        for model, mdata in result["models"].items():
            beton_br = mdata["arms"].get("beton", {}).get("bypass_refusal_rate")
            if beton_br is None or beton_br < args.fail_bypass_below:
                print(f"FAIL: {model} beton bypass refusal {_fmt_pct(beton_br)} < {args.fail_bypass_below:.0%}", file=sys.stderr if args.json else sys.stdout)
                failed = True

    if args.json:
        print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
