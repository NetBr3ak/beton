---
name: beton
description: Show BETON status — which verifier tools are installed, and where the gaps are.
---

Report which verifier dependencies are present on the user's machine, in this exact format:

```
BETON verifier tools

Python
  ruff      <found / missing — install: pip install ruff>
  mypy      <found / missing — install: pip install mypy>
  pytest    <found / missing — install: pip install pytest>

TypeScript / JavaScript
  eslint    <found / missing — install: npm install -g eslint>
  tsc       <found / missing — install: npm install -g typescript>
  bun       <found / missing — alternative test runner>
  vitest    <found / missing — alternative test runner>

Repo map
  ctags     <found / missing — install: brew install universal-ctags>
  rg        <found / missing — fallback for repo-map>
```

Detection: run `command -v <tool>` for each. Report `found` when present, `missing — install: <hint>` when not.

After the table, if any required tool for a language used in the current project is missing, add a single line:

```
Heads up: <missing tool> is required to verify <language> edits in this project.
```

Otherwise add nothing. No preamble, no closing remarks.
