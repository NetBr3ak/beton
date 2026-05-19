# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x   | ✓ |
| < 0.5   | ✗ |

## Reporting a vulnerability

If you find a security issue (sandbox escape, hook injection, credential leak via stats files, etc.), please report it privately rather than opening a public issue.

Email: szymon.jendryczkos@gmail.com

Include:

- A description of the issue
- Steps to reproduce
- Affected version and platform
- A suggested fix if you have one

I'll acknowledge within 72 hours and aim to ship a patch within two weeks for confirmed issues. Once a patch ships, I'll publish the disclosure in the changelog.

## Threat model

BETON is a Claude Code plugin. It runs lint, typecheck, and tests against files the user authorizes Claude to edit. The threat model assumes:

- The human running Claude Code is the trusted actor.
- The LLM is semi-trusted. It might make mistakes, hallucinate paths, or attempt shortcuts, but it isn't actively trying to compromise the host.
- The eval scripts (`evals/llm_run.py`, `evals/swebench_mini.py`) accept model responses as input and write to temp directories. Path-traversal protection is in place; treat any unexpected file write outside the work directory as a security issue worth reporting.

Stats and state files live under `~/.claude/`. They contain counters and the path of the last edited file. They do not contain code, credentials, or secrets.

## Out of scope

- Adversarial LLM behavior beyond the documented bypass patterns (the guard is a whitelist; see "What this isn't" in the README).
- Issues in third-party tools BETON shells out to (ruff, mypy, eslint, etc.). Report those upstream.
- Vulnerabilities in dependencies of `evals/llm_run.py` (the `anthropic` Python SDK). Report to Anthropic.
