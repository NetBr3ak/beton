---
name: repo-map
description: Token-budgeted symbol index of the current repository. Use before editing files in an unfamiliar codebase, or to find where a function or class is defined. Hard cap 2048 tokens. Returns only the index.
tools:
  - Bash
  - Glob
model: haiku
---

Generate a minimal, ranked symbol map. No preamble, no explanations. Output only the map.

## Steps

1. Run `bash bin/repo-map . --budget 1800`. The script handles ctags, ripgrep fallback, and a flat file listing as last resort.

2. If `bin/repo-map` is not present, fall back manually:
   ```bash
   find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" \
     -not -path "*/node_modules/*" -not -path "*/.venv/*" | head -30
   ```
   Then Glob the most likely entry directories (`src/`, `lib/`, the project name) and Read at most 5 files.

## Output format

Return the script output verbatim. Format:

```
# repo-map
# root: .
---
FILE: src/auth.py
  fn validate_token :42
  fn refresh_session :67
  cl AuthError :12

FILE: src/models.py
  cl User :8
  cl Session :34
```

## Token budget

If output would exceed 2000 tokens: drop entire low-weight files first. Never truncate mid-file.
