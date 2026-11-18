# BETON standalone CLI

Find Python tests affected by a source edit, without running project code or
installing Claude Code hooks. All three distributions use the same Python
static-import engine as the BETON plugin.

## Install from the GitHub Release

Download the archives from [BETON v0.3.0](https://github.com/NetBr3ak/beton/releases/tag/v0.3.0).
For example, install the Python wheel directly:

```sh
pip install https://github.com/NetBr3ak/beton/releases/download/v0.3.0/beton_checks-0.3.0-py3-none-any.whl
```

The release also provides an npm `.tgz`, a Python source archive, and a Cargo
`.crate` source archive, with `SHA256SUMS`. npm accepts the downloaded `.tgz`
path. To install the crate before registry publication, extract it and run
`cargo install --path beton-checks-0.3.0 --offline --locked`.

## Registry installation after publication

These commands require `beton-checks` to be published on the chosen registry.
An archive on GitHub does not mean a registry has accepted the package.

```sh
pip install beton-checks
npm install --global beton-checks
cargo install beton-checks
```

These are alternatives. Each installs the command `beton`. Do not install them
together into the same command directory. The npm archive also includes the
Claude Code plugin, but does not enable it. To use it for one session after a
local npm install, run `claude --plugin-dir ./node_modules/beton-checks`.

Python 3.11 or later is required for every distribution. The npm package also
requires Node.js 22.13 or later. Cargo builds a native launcher with no Rust
dependencies, not a native Python parser. npm and Cargo use `python3` on Unix
and `python` on Windows. Set `BETON_PYTHON` to an interpreter path if needed.
The Python package has no runtime dependencies. Installation does not install
checkers or hooks, change Claude settings, or download a Python interpreter.

## Use

```sh
beton affected src/shop/pricing.py
beton affected src/shop/pricing.py --root . --json
python -m beton_checks affected src/shop/pricing.py
```

The command prints one absolute test path per line, or a JSON array with
`--json`. An empty result is successful. It does not run the selected tests.
The default root is the nearest ancestor containing a project marker, such as
`pyproject.toml`, or `.git`. Without a marker it uses the current directory.
Use `--root` when that boundary is not the project you want to inspect.

Discovery follows direct and transitive local Python imports, package
initializers and `conftest.py` dependencies. It recognizes `test_*.py` and
`*_test.py`, excludes nested projects and dependency directories, and does not
execute imports. Unparseable Python causes conservative selection of all
discovered tests. Dynamic imports and custom pytest naming are not resolved.
A file with no static path to a test can produce no results. Keep the full
test suite in CI. This standalone command does not provide the plugin's
filename-based matching or verification hooks.

Exit status is 0 after successful discovery, 2 for invalid arguments, and 1
for discovery or interpreter errors. Use `beton --help` for command help.
