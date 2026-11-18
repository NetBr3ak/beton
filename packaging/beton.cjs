#!/usr/bin/env node
'use strict';

const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { spawnSync } = require('node:child_process');

const root = join(__dirname, '..');
const read = (path) => readFileSync(join(root, path), 'utf8');
const python = process.env.BETON_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const result = spawnSync(python, [
  '-I', '-c', read('packaging/bootstrap.py'),
  read('src/beton_checks/discovery.py'), read('src/beton_checks/__main__.py'),
  ...process.argv.slice(2),
], { stdio: 'inherit' });

if (result.error) {
  console.error(`beton: cannot start ${python}: ${result.error.message}. Install Python 3.11+ or set BETON_PYTHON.`);
  process.exit(1);
}
if (result.signal) {
  process.kill(process.pid, result.signal);
} else {
  process.exit(result.status === null ? 1 : result.status);
}
