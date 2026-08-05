#!/usr/bin/env bash
# Integration smoke test: validates plugin components are wired correctly.
source "$(dirname "$0")/helpers.sh"
isolate_home

echo "=== BETON integration smoke test ==="

# 1. Plugin manifest structure
python3 -c "
import json
p = json.load(open('.claude-plugin/plugin.json'))
assert 'PostToolUse' in p['hooks'], 'PostToolUse hook missing'
assert 'SessionStart' in p['hooks'], 'SessionStart hook missing'
assert 'UserPromptSubmit' not in p['hooks'], 'UserPromptSubmit hook should be absent'
assert 'statusLine' in p, 'statusLine missing from plugin.json'
assert 'command' in p['statusLine'], 'statusLine.command missing'
" && ok "plugin.json: SessionStart + PostToolUse + statusLine present" || not_ok "plugin.json: manifest incorrect"

# 2. Hooks exist and are executable
for h in hooks/post-tool-verify.sh hooks/pre-tool-guard.sh hooks/statusline.sh; do
  [ -x "$h" ] && ok "$h: exists and executable" || not_ok "$h: missing or not executable"
done
for h in hooks/beton-activate.js hooks/beton-config.js hooks/_guard_eval.py; do
  [ -f "$h" ] && ok "$h: exists" || not_ok "$h: missing"
done

# 3. All bin/ scripts exist and are executable
for bin in bin/lint-file bin/typecheck-file bin/run-affected-tests bin/repo-map bin/beton-session-stats bin/beton-stats; do
  [ -x "$bin" ] && ok "$bin: exists and executable" || not_ok "$bin: missing or not executable"
done

# 4. Every markdown file that opens with a frontmatter block parses as YAML.
# Presence alone is not enough: Claude Code loads these as YAML, so an unquoted
# value carrying a colon or a stray quote breaks the command without touching prose.
if python3 -c "import yaml" 2>/dev/null; then
  python3 -c "
import pathlib, re, sys, yaml
bad = []
for f in sorted(pathlib.Path('.').rglob('*.md')):
    m = re.match(r'^---\n(.*?)\n---\n', f.read_text(encoding='utf-8'), re.DOTALL)
    if not m:
        continue
    try:
        yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        bad.append(f'{f}: {str(e).splitlines()[0]}')
if bad:
    sys.exit('\n'.join(bad))
" && ok "frontmatter: every markdown block parses as YAML" || not_ok "frontmatter: invalid YAML"
else
  ok "pyyaml not installed, skipping frontmatter parse test"
fi

# 6. Verifier blocks on dirty Python (only if ruff is available, otherwise skip)
if command -v ruff &>/dev/null; then
  DIRTY=$(python3 -c "import tempfile; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_smoke_'); print(f.name); f.close()")
  printf 'import unused_module\nx = 1\n' > "$DIRTY"
  EVENT=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "$DIRTY")
  VERIFIER_OUT=$(echo "$EVENT" | bash hooks/post-tool-verify.sh 2>/dev/null || true)
  if [ -n "$VERIFIER_OUT" ]; then
    DECISION=$(echo "$VERIFIER_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision',''))" 2>/dev/null || echo "")
    check_eq "$DECISION" "block" "PostToolUse verifier: blocks on lint error"
  else
    not_ok "PostToolUse verifier: expected block JSON, got empty output"
  fi
  rm -f "$DIRTY"
else
  ok "ruff not installed, skipping verifier block test"
fi

# 7. Statusline: pass state → green output
python3 -c "
import json, os
path = os.path.expanduser('~/.claude/.beton-state')
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump({'status': 'pass', 'file': 'x.py', 'errors': 0}, open(path, 'w'))
"
SL_OUT=$(bash hooks/statusline.sh 2>/dev/null || true)
echo "$SL_OUT" | grep -q "BETON" \
  && ok "statusline: pass state renders BETON badge" \
  || not_ok "statusline: pass state output missing BETON"

# 8. Statusline: block state → red output with error count
python3 -c "
import json, os
path = os.path.expanduser('~/.claude/.beton-state')
json.dump({'status': 'block', 'file': 'x.py', 'errors': 3}, open(path, 'w'))
"
SL_OUT=$(bash hooks/statusline.sh 2>/dev/null || true)
echo "$SL_OUT" | grep -q "3" \
  && ok "statusline: block state renders error count" \
  || not_ok "statusline: block state missing error count"

# 9. Statusline: no state file → empty output (silent)
rm -f ~/.claude/.beton-state
SL_OUT=$(bash hooks/statusline.sh 2>/dev/null || true)
check_eq "$SL_OUT" "" "statusline: no state file → empty (silent)"

# 10. SessionStart hook: runs without error, resets state, emits BETON context
if command -v node &>/dev/null; then
  rm -f ~/.claude/.beton-state
  ACTIVATE_OUT=$(CLAUDE_PLUGIN_ROOT="$(pwd)" node hooks/beton-activate.js 2>/dev/null || true)
  echo "$ACTIVATE_OUT" | grep -q "BETON" \
    && ok "beton-activate.js: emits BETON context" \
    || not_ok "beton-activate.js: missing BETON in output"
  STATE=$(python3 -c "import json,os; p=os.path.expanduser('~/.claude/.beton-state'); d=json.load(open(p)); print(d.get('status',''))" 2>/dev/null || echo "")
  check_eq "$STATE" "ready" "beton-activate.js: resets state to 'ready'"
else
  ok "node not installed, skip activate hook test"
fi

# 11. Verifier writes state file after run
if command -v ruff &>/dev/null; then
  rm -f ~/.claude/.beton-state
  DIRTY=$(python3 -c "import tempfile; f=tempfile.NamedTemporaryFile(suffix='.py',dir='/tmp',delete=False,prefix='beton_smoke_'); print(f.name); f.close()")
  printf 'import unused_module\nx = 1\n' > "$DIRTY"
  EVENT=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'path':sys.argv[2]},'tool_response':{'output':'ok'}}))" -- "$DIRTY")
  echo "$EVENT" | bash hooks/post-tool-verify.sh > /dev/null 2>&1 || true
  STATE=$(python3 -c "import json,os; p=os.path.expanduser('~/.claude/.beton-state'); d=json.load(open(p)); print(d.get('status',''))" 2>/dev/null || echo "")
  check_eq "$STATE" "block" "verifier: writes block state to flag file"
  rm -f "$DIRTY"
else
  ok "ruff not installed, skipping state file write test"
fi

report
