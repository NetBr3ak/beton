#!/usr/bin/env bash
# Download an existing release once; never build publisher inputs from HEAD.
set -euo pipefail

RELEASE_TAG="$1"
RELEASE_ASSETS="$2"
RELEASE_OUTPUT="$3"
if [[ ! "$RELEASE_TAG" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "release_tag must be an explicit stable tag such as v0.3.0" >&2
  exit 1
fi
RELEASE_VERSION="${RELEASE_TAG#v}"
RELEASE_SCRIPT="$(cd "$(dirname "$0")" && pwd)"
RELEASE_METADATA=$(mktemp -d "${TMPDIR:-/tmp}/beton-release-metadata.XXXXXX")
trap 'rm -rf "$RELEASE_METADATA"' EXIT

gh release view "$RELEASE_TAG" --repo NetBr3ak/beton \
  --json tagName,isDraft,isPrerelease,assets > "$RELEASE_METADATA/release.json"
jq -e --arg tag "$RELEASE_TAG" \
  '.tagName == $tag and (.isDraft | not) and (.isPrerelease | not)' \
  "$RELEASE_METADATA/release.json" >/dev/null
printf '%s\n' \
  "beton-checks-$RELEASE_VERSION.crate" \
  "beton-checks-$RELEASE_VERSION.tgz" \
  "beton_checks-$RELEASE_VERSION-py3-none-any.whl" \
  "beton_checks-$RELEASE_VERSION.tar.gz" SHA256SUMS | LC_ALL=C sort > "$RELEASE_METADATA/expected"
jq -r '.assets[].name' "$RELEASE_METADATA/release.json" | LC_ALL=C sort > "$RELEASE_METADATA/actual"
diff -u "$RELEASE_METADATA/expected" "$RELEASE_METADATA/actual"
RELEASE_COMMIT=$(gh api "repos/NetBr3ak/beton/commits/$RELEASE_TAG" --jq .sha)
[[ "$RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
mkdir "$RELEASE_ASSETS"
gh release download "$RELEASE_TAG" --repo NetBr3ak/beton --dir "$RELEASE_ASSETS"
RELEASE_MANIFEST_SHA=$(sha256sum "$RELEASE_ASSETS/SHA256SUMS" | cut -d ' ' -f 1)
bash "$RELEASE_SCRIPT/check-release-assets.sh" "$RELEASE_ASSETS" "$RELEASE_VERSION" "$RELEASE_MANIFEST_SHA"
printf 'version=%s\ncommit=%s\nmanifest_sha=%s\n' \
  "$RELEASE_VERSION" "$RELEASE_COMMIT" "$RELEASE_MANIFEST_SHA" >> "$RELEASE_OUTPUT"
