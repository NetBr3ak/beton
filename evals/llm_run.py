#!/usr/bin/env python3
"""
BETON evals, stage 1: API calls.

Runs three arms (baseline / terse / beton) on a tagged prompt set, saves
a JSON snapshot. Run this once to generate data; commit the snapshot; CI
calls measure.py offline.

Prompt schema (evals/prompts/en.json):
    [
        {"id": "bug-01",    "kind": "bug",         "category": "...",
         "prompt": "..."},
        {"id": "bypass-01", "kind": "bypass_noqa", "prompt": "..."},
        ...
    ]

Two measurement signals come out of this snapshot:

* bug prompts → does the response invoke Phase 1 / localize first?
* bypass prompts → does the response refuse the shortcut?

Usage:
    python3 evals/llm_run.py                  # all models
    python3 evals/llm_run.py --model haiku    # single model
    python3 evals/llm_run.py --help
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
PROMPTS_FILE = Path(__file__).parent / "prompts" / "en.json"
LEGACY_PROMPTS_FILE = Path(__file__).parent / "prompts" / "en.txt"

MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}

TERSE_SYSTEM = "Answer concisely. Fix issues directly."
MAX_TOKENS = 256


def load_skill() -> tuple[str, str]:
    path = ROOT / "skills" / "beton-swebench" / "SKILL.md"
    raw = path.read_text()
    if raw.startswith("---"):
        end = raw.index("---", 3)
        raw = raw[end + 3:].lstrip()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return raw, sha


def load_prompts() -> list[dict]:
    """Prefer en.json; fall back to en.txt for older snapshots."""
    if PROMPTS_FILE.exists():
        data = json.loads(PROMPTS_FILE.read_text())
        return [
            {
                "id": p.get("id", f"prompt-{i:02d}"),
                "kind": p.get("kind", "bug"),
                "category": p.get("category", "general"),
                "prompt": p["prompt"],
            }
            for i, p in enumerate(data)
        ]
    if LEGACY_PROMPTS_FILE.exists():
        return [
            {"id": f"legacy-{i:02d}", "kind": "bug", "category": "legacy", "prompt": line.strip()}
            for i, line in enumerate(LEGACY_PROMPTS_FILE.read_text().splitlines())
            if line.strip()
        ]
    raise FileNotFoundError(f"No prompt file at {PROMPTS_FILE} or {LEGACY_PROMPTS_FILE}")


def call_with_retry(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    for attempt in range(4):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)
    return client.messages.create(**kwargs)


def get_text(msg: anthropic.types.Message) -> str:
    b = msg.content[0]
    return b.text if hasattr(b, "text") else ""


def run(target_model: str | None = None) -> None:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    skill_content, skill_sha = load_skill()
    prompts = load_prompts()
    models = {target_model: MODELS[target_model]} if target_model else MODELS

    results: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "skill_sha256": skill_sha,
        "prompt_count": len(prompts),
        "models": {},
    }

    arms = [
        ("baseline", None),
        ("terse",    TERSE_SYSTEM),
        ("beton",    TERSE_SYSTEM + "\n\n" + skill_content),
    ]

    for model_key, model_id in models.items():
        print(f"\n=== {model_key} ===", flush=True)
        model_data: dict = {"arms": {}}

        for arm_name, system in arms:
            print(f"  {arm_name}", end="", flush=True)
            responses = []
            for p in prompts:
                msg = call_with_retry(
                    client,
                    model=model_id,
                    max_tokens=MAX_TOKENS,
                    **({"system": system} if system else {}),
                    messages=[{"role": "user", "content": p["prompt"]}],
                )
                responses.append({
                    "id": p["id"],
                    "kind": p["kind"],
                    "category": p.get("category", "general"),
                    "prompt": p["prompt"],
                    "response": get_text(msg),
                    "output_tokens": msg.usage.output_tokens,
                    "input_tokens": msg.usage.input_tokens,
                })
                print(".", end="", flush=True)
            model_data["arms"][arm_name] = responses
            print(f" ({len(responses)} calls)")

        results["models"][model_key] = model_data

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    archived = SNAPSHOTS_DIR / f"results-{stamp}.json"
    canonical = SNAPSHOTS_DIR / "results.json"
    archived.write_text(json.dumps(results, indent=2))
    canonical.write_text(json.dumps(results, indent=2))
    print(f"\nSnapshot written: {canonical}")
    print(f"Archive copy:     {archived}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=list(MODELS.keys()), default=None,
                   help="Run a single model rather than all three")
    args = p.parse_args()
    run(args.model)


if __name__ == "__main__":
    main()
