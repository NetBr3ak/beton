#!/usr/bin/env bash
# Check transferred release bytes against the manifest approved during staging.
set -euo pipefail

RELEASE_ASSETS="$1"
RELEASE_VERSION="$2"
RELEASE_MANIFEST_SHA="$3"
[[ "$RELEASE_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$RELEASE_MANIFEST_SHA" =~ ^[0-9a-f]{64}$ ]]
cd "$RELEASE_ASSETS"

RELEASE_CHECK=$(mktemp -d "${TMPDIR:-/tmp}/beton-release-assets.XXXXXX")
trap 'rm -rf "$RELEASE_CHECK"' EXIT
printf '%s\n' \
  "beton-checks-$RELEASE_VERSION.crate" \
  "beton-checks-$RELEASE_VERSION.tgz" \
  "beton_checks-$RELEASE_VERSION-py3-none-any.whl" \
  "beton_checks-$RELEASE_VERSION.tar.gz" | LC_ALL=C sort > "$RELEASE_CHECK/packages"
{
  cat "$RELEASE_CHECK/packages"
  echo SHA256SUMS
} | LC_ALL=C sort > "$RELEASE_CHECK/expected"
find . -mindepth 1 -maxdepth 1 -print | sed 's|^./||' | LC_ALL=C sort > "$RELEASE_CHECK/actual"
diff -u "$RELEASE_CHECK/expected" "$RELEASE_CHECK/actual"
[[ -z "$(find . -mindepth 1 -maxdepth 1 ! -type f -print)" ]]
printf '%s  SHA256SUMS\n' "$RELEASE_MANIFEST_SHA" | sha256sum -c -
awk 'NF != 2 || length($1) != 64 || $1 !~ /^[0-9a-f]+$/ { exit 1 }' SHA256SUMS
awk '{ print $2 }' SHA256SUMS | LC_ALL=C sort > "$RELEASE_CHECK/manifest"
diff -u "$RELEASE_CHECK/packages" "$RELEASE_CHECK/manifest"
sha256sum -c SHA256SUMS
