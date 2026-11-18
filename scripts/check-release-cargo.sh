#!/usr/bin/env bash
# Compare a clean tagged checkout's normalized Cargo package with the release.
set -euo pipefail

RELEASE_ARCHIVES="$1"
RELEASE_SOURCE="$2"
RELEASE_CHECK="$3"
RELEASE_VERSION="$4"

cargo package --offline --locked --manifest-path "$RELEASE_SOURCE/Cargo.toml" --target-dir "$RELEASE_CHECK/target"
mkdir -p "$RELEASE_CHECK/published" "$RELEASE_CHECK/repackaged"
tar -xzf "$RELEASE_ARCHIVES/beton-checks-$RELEASE_VERSION.crate" -C "$RELEASE_CHECK/published"
tar -xzf "$RELEASE_CHECK/target/package/beton-checks-$RELEASE_VERSION.crate" -C "$RELEASE_CHECK/repackaged"
diff -r "$RELEASE_CHECK/published" "$RELEASE_CHECK/repackaged"
echo "Cargo normalized source matches every published file, including manifests and VCS metadata."
