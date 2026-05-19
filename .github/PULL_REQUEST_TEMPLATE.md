## What this PR does

<!-- One or two sentences describing the change. -->

## Why

<!-- The motivation. If this fixes an issue, link it: "Closes #N". -->

## How to verify

```bash
# Commands a reviewer can run to confirm the change works.
for t in tests/test-*.sh; do bash "$t"; done
```

## Checklist

- [ ] All existing tests pass (`for t in tests/test-*.sh; do bash "$t"; done`)
- [ ] New tests added if behavior changed
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` if user-visible
- [ ] README updated if user-visible behavior changed
- [ ] No em-dashes in new prose (`grep -nF '—' README.md` returns nothing)
