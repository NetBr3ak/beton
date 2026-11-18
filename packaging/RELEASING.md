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

The `standalone packages` workflow has a manual `registry` choice:

| Mode | Input and result |
|---|---|
| `verify` | Builds and checks the current checkout. Does not publish. |
| `stage` | Requires `release_tag`, such as `v0.3.0`. Downloads and verifies that public GitHub Release. Does not publish. |
| `npm`, `pypi`, `crates` | Requires `release_tag`. Publishes one registry using the verified release, only from a workflow run on `master`. |

Publishing never rebuilds npm or Python archives from the current checkout.
The release must have exactly four versioned package archives and SHA256SUMS.
Staging uses `gh` to select an existing stable release and its tag's exact
commit. It downloads all five files and checks their names and SHA256SUMS.
Every archive name must carry the selected version. Missing checksums, extra
files, and changed packages stop publication. Stage records the manifest's
SHA-256 digest. Each publisher checks that digest and every package checksum
again after the Actions transfer, without another remote lookup. npm and PyPI
receive the downloaded bytes unchanged. Package name and version metadata
are checked by the build and installed-consumer checks before release.

Cargo checks out the tag's exact commit and packages that clean source.
`diff -r` compares every extracted file against the published crate, including
both Cargo manifests and VCS metadata. No file is ignored or normalized by a
custom comparator. A difference stops publication. Cargo still repackages
during `cargo publish`, so install and check the registry download afterwards.

The workflow stays on `master` for trusted-publisher identity, even when the
selected release tag is older. Only publish jobs have OIDC permission. A failed
registry can be retried without publishing the others again. Check the public
registry version and digest before retrying an upload that might have finished.

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

For a local retry of an existing release, stage its public archives into an
empty directory, then check them immediately before publishing:

```sh
RELEASE_TAG=v0.3.0
RELEASE_VERSION=${RELEASE_TAG#v}
bash scripts/stage-release.sh "$RELEASE_TAG" release-assets release-outputs.txt
npm publish "./release-assets/beton-checks-$RELEASE_VERSION.tgz" --access public
uv publish "release-assets/beton_checks-$RELEASE_VERSION-py3-none-any.whl" "release-assets/beton_checks-$RELEASE_VERSION.tar.gz"
```

The staging scripts use Bash, `gh`, `jq` and `sha256sum`, as supplied by
the workflow's Ubuntu runner. The staging token has only `contents: read`.

Use the workflow for Cargo so it checks out and compares the clean tagged
source before publishing. Do not run `cargo publish` from a newer checkout
that still carries the release's version number.

If account login blocks a registry, attach the tested archives and SHA256SUMS
to the public GitHub Release. Report that channel separately. A GitHub archive
does not mean the package is available through a registry.
