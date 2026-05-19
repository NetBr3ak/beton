// Shared config resolution for beton hooks.
// Priority: BETON_MODE env var > XDG config file > hardcoded default.
// XDG: $XDG_CONFIG_HOME/beton/config.json → ~/.config/beton/config.json (Unix)
//                                          → %APPDATA%\beton\config.json (Windows)

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const VALID_MODES = ['strict', 'standard', 'audit', 'off'];
const DEFAULT_MODE = 'strict';

function getConfigDir() {
  if (process.env.XDG_CONFIG_HOME) {
    return path.join(process.env.XDG_CONFIG_HOME, 'beton');
  }
  if (process.platform === 'win32') {
    const appdata = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
    return path.join(appdata, 'beton');
  }
  return path.join(os.homedir(), '.config', 'beton');
}

function getConfigPath() {
  return path.join(getConfigDir(), 'config.json');
}

function getMode() {
  // 1. Env var
  const envMode = (process.env.BETON_MODE || '').toLowerCase();
  if (VALID_MODES.includes(envMode)) return envMode;

  // 2. Config file
  try {
    const raw = fs.readFileSync(getConfigPath(), 'utf8');
    const cfg = JSON.parse(raw);
    const fileMode = (cfg.mode || '').toLowerCase();
    if (VALID_MODES.includes(fileMode)) return fileMode;
  } catch (_) {
    // Missing or invalid config; fall through to default.
  }

  // 3. Default
  return DEFAULT_MODE;
}

module.exports = { getMode, getConfigDir, getConfigPath, VALID_MODES };
