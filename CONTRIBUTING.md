# Contributing

Use Python 3.11 or later, Bash and Node.js. Install `ruff`, `mypy`, `pytest` and `pyyaml` in a virtual environment. Install ESLint and TypeScript to run their optional checker tests.

Run `bash scripts/check.sh` from the repository root. It checks syntax, production Python lint, the guard's types and the offline tests. The runner isolates state from your real Claude Code settings and returns nonzero if any check fails. There is no build step.

Existing tests define the current behavior. Add a regression test before fixing a bug. Keep a test with the fix it proves. Do not weaken assertions or add skips to get a passing result. Demo source has an intentional bug and is excluded from production lint.

The shell tests exercise hooks and installed checkers. New Python regression tests use the standard library's `unittest`. The files named `test-api-*.py` call paid model APIs and are not part of the offline runner. Never include API credentials or session logs in a patch.

For hook changes, validate the manifests with `claude plugin validate .` if Claude Code is installed. This validates metadata without installing the plugin. Include the command, exit code and any warnings in your pull request.

Use a focused Conventional Commit subject. Explain the behavior change and how you tested it. Report security issues using [SECURITY.md](SECURITY.md), not a public issue with exploit details or credentials.
