#!/usr/bin/env node
// SessionStart hook: inject BETON context, reset state file, nudge missing statusLine.
// Reads SKILL.md at runtime so skill edits take effect next session automatically.
'use strict';

const fs   = require('fs');
const os   = require('os');
const path = require('path');
const { getMode } = require('./beton-config');

const PLUGIN_ROOT = process.env.CLAUDE_PLUGIN_ROOT
  || path.resolve(__dirname, '..');

const STATE_FILE    = path.join(os.homedir(), '.claude', '.beton-state');
const SETTINGS_FILE = path.join(os.homedir(), '.claude', 'settings.json');

function resetState() {
  try {
    const dir = path.dirname(STATE_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(STATE_FILE, JSON.stringify({ status: 'ready', file: '', errors: 0 }));
  } catch (_) { /* best-effort */ }
}

function loadSkill(name) {
  try {
    const p    = path.join(PLUGIN_ROOT, 'skills', name, 'SKILL.md');
    let content = fs.readFileSync(p, 'utf8');
    if (content.startsWith('---')) {
      const end = content.indexOf('---', 3);
      if (end !== -1) content = content.slice(end + 3).trimStart();
    }
    return content;
  } catch (_) {
    return null;
  }
}

function hasStatusLine() {
  try {
    const cfg = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'));
    return !!(cfg.statusLine && cfg.statusLine.command);
  } catch (_) {
    return false;
  }
}

const mode = getMode();

resetState();

const lines = [`BETON active (mode: ${mode}). Verifier runs on every Write/Edit/MultiEdit; PreToolUse guard refuses bypass shortcuts.\n`];

if (mode !== 'off') {
  const skill = loadSkill('beton-swebench');
  if (skill) {
    lines.push('## Active skill: beton-swebench\n');
    lines.push(skill);
  } else {
    lines.push('Skill: Phase 1 Localize → Phase 2 Fix → Phase 3 Validate. Do not skip phases.\n');
  }
}

if (!hasStatusLine()) {
  lines.push('\nTip: configure statusLine to see BETON ✓/✗ in your prompt.');
  lines.push('  Settings → statusLine.command: bash $CLAUDE_PLUGIN_ROOT/hooks/statusline.sh');
}

process.stdout.write(lines.join('\n'));
