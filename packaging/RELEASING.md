# Release standalone packages

The package identity is `beton-checks` on npm, PyPI and crates.io. Each
distribution provides `beton affected`. These packages do not install the
Claude Code plugin.

Run the source gate and consumer checks before publication:

```sh
bash scripts/check.sh
python3 scripts/check-packages.py
```

The second command writes four tested archives to `dist/`. It builds the
Python wheel from its source distribution and installs both independently.
It installs the npm tarball with lifecycle scripts disabled. It extracts the
Cargo package and installs the extracted source offline, with default features
disabled. The launcher has no Rust dependencies.

The `standalone packages` workflow has a manual `registry` choice. `verify`
builds and stores artifacts without publishing. Other choices publish one
registry only, from `master`, after all checks pass. A failed registry can be
retried without publishing the others again. Compare the public registry
version and archive digest before retrying a version that might have uploaded.

## Authentication

No credentials belong in the repository or release notes. Use an authenticated
local package-manager session, or configure the corresponding GitHub secret:

| Registry | GitHub secret or trusted publisher |
|---|---|
| npm | `NPM_TOKEN`, or npm trusted publisher for `NetBr3ak/beton`, workflow `packages.yml` |
| PyPI | `PYPI_TOKEN`, or PyPI trusted publisher for `NetBr3ak/beton`, workflow `packages.yml` |
| crates.io | `CARGO_REGISTRY_TOKEN`, or crates.io trusted publisher for `NetBr3ak/beton`, workflow `packages.yml` |

npm trusted publishing requires an existing package with the publisher
configured. The first publish needs the owner's authenticated account or
token. PyPI supports a pending trusted publisher for a new package. Register
the pending publisher under the owner's account before the first CI upload.
Creating a workflow alone does not register either trusted publisher.
The Cargo job uses Rust's official `crates-io-auth-action` when no registry
token is configured. Register a crates.io trusted publisher for the existing
crate before using that path. A new crate still needs its first upload from
the owner's authenticated account.

Official setup references: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/),
[PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[Cargo publishing](https://doc.rust-lang.org/cargo/reference/publishing.html),
[crates.io trusted publishing](https://crates.io/docs/trusted-publishing).

For a local release, publish the tested npm tarball and Python archives. Cargo
packages and verifies the committed source before upload:

Cargo repackages source during `cargo publish`. The registry download must
be installed and checked again after upload. The local `.crate` check alone
does not prove what crates.io serves.

```sh
npm publish ./dist/beton-checks-0.3.0.tgz --access public
uv publish dist/beton_checks-0.3.0-py3-none-any.whl dist/beton_checks-0.3.0.tar.gz
cargo publish --locked
```

If account login blocks a registry, attach the tested archives and SHA256SUMS
to the public GitHub Release. Report that channel separately. A GitHub archive
does not mean the package is available through a registry.
