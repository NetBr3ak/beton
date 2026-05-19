#!/usr/bin/env bash
source "$(dirname "$0")/helpers.sh"

# plugin.json: valid JSON, PreToolUse + PostToolUse + SessionStart + statusLine
python3 -c "
import json
with open('.claude-plugin/plugin.json') as f:
    p = json.load(f)
for field in ['name','description','hooks']:
    assert field in p, f'missing field: {field}'
for hook in ['SessionStart', 'PreToolUse', 'PostToolUse']:
    assert hook in p['hooks'], f'{hook} hook missing'
assert 'UserPromptSubmit' not in p['hooks'], 'UserPromptSubmit hook should be absent'
assert 'statusLine' in p, 'statusLine missing'
for hook_name in ('PreToolUse', 'PostToolUse'):
    entries = p['hooks'][hook_name]
    assert any('matcher' in entry for entry in entries if isinstance(entry, dict)), \
        f'{hook_name} missing matcher'
print('OK')
" 2>&1 | grep -q "^OK$" \
  && ok "plugin.json: valid, SessionStart + PreToolUse + PostToolUse + statusLine" \
  || not_ok "plugin.json: invalid or hook set wrong"

# marketplace.json: valid JSON with required fields
python3 -c "
import json
with open('.claude-plugin/marketplace.json') as f:
    m = json.load(f)
assert 'name' in m
assert 'plugins' in m
print('OK')
" 2>&1 | grep -q "^OK$" \
  && ok "marketplace.json: valid" \
  || not_ok "marketplace.json: invalid"

report
