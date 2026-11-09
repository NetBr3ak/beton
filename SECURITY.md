# Security policy

## Supported version

The current plugin manifest declares version `0.1.0`. Report issues against the current default branch. No response or patch deadline is promised.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/NetBr3ak/beton/security/advisories/new) if the repository enables it. If that option is unavailable, open an issue asking for a private reporting channel. Do not include exploit details, credentials or private source in a public issue.

Include the affected version, platform, steps to reproduce and expected behavior.

## Threat model

BETON runs project checkers with the permissions of the user running Claude Code. Linters, test runners, plugins and project configuration can execute code. Use it only with projects and tools you trust.

The bypass guard detects listed patterns. It is not a sandbox and cannot prevent all test weakening or shell-based edits. Post-edit verification does not roll back changes.

The optional eval harness restricts model file replacements to scenario sources and checks path containment. Running model-generated Python still executes untrusted code. Run API experiments in a disposable isolated environment without host credentials or private files. A temporary directory alone is not isolation.

State and counters live under `~/.claude/`. The state includes the last edited file path. Do not publish these files or Claude session logs.
