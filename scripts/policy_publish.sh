#!/usr/bin/env bash
# Praesidio — package, sign, and publish a policy bundle to an OCI registry.
#
# Usage:
#   scripts/policy_publish.sh [-d DIR] [-r REGISTRY/REPO] [-t TAG] [--no-sign]
#
#   -d DIR        Source policy directory (default: ./examples/policies)
#   -r REGISTRY   Target OCI repo (default: ${PRAESIDIO_POLICY_REPO:-ghcr.io/praesidio/policies})
#   -t TAG        Tag to publish (default: timestamp; recommended: semver)
#   --no-sign     Skip cosign signing (NOT RECOMMENDED — for local dry runs only)
#
# Requires: oras, cosign. Both must be on PATH.
#   oras:   https://oras.land/docs/installation
#   cosign: https://docs.sigstore.dev/cosign/installation
#
# Behaviour:
#   1. Validate the bundle locally via scripts/seed_policies.py --no-reload.
#   2. Tar the directory into a deterministic archive (sorted, mtime=0).
#   3. oras push the archive as an OCI artefact with media type
#      application/vnd.praesidio.policy-bundle.v1+tar.
#   4. cosign sign --yes (keyless via Fulcio by default; or COSIGN_KEY for KMS).
#   5. Print the published reference (registry/repo:tag@sha256:...) and the
#      verification one-liner.

set -euo pipefail

SRC_DIR="./examples/policies"
REPO="${PRAESIDIO_POLICY_REPO:-ghcr.io/praesidio/policies}"
TAG="$(date -u +%Y%m%d%H%M%S)"
SIGN="1"

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -d) SRC_DIR="$2"; shift 2 ;;
    -r) REPO="$2"; shift 2 ;;
    -t) TAG="$2"; shift 2 ;;
    --no-sign) SIGN="0"; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required tool not found on PATH: $1" >&2
    echo "        install: $2" >&2
    exit 2
  fi
}

require oras   "https://oras.land/docs/installation"
require tar    "(install via your package manager)"
if [ "$SIGN" = "1" ]; then
  require cosign "https://docs.sigstore.dev/cosign/installation"
fi

if [ ! -d "$SRC_DIR" ]; then
  echo "ERROR: source dir not found: $SRC_DIR" >&2
  exit 2
fi

echo ":: validating bundle at $SRC_DIR"
if command -v python >/dev/null 2>&1 && [ -f scripts/seed_policies.py ]; then
  python scripts/seed_policies.py --bundle "$SRC_DIR" --no-reload
else
  echo "   (skipping seed validation — python or seed_policies.py not available)"
fi

WORK="$(mktemp -d -t praesidio-bundle.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

ARCHIVE="$WORK/bundle.tar"
echo ":: packaging bundle -> $ARCHIVE"
# Deterministic tar: sorted entries, normalised owner/perms/mtime.
( cd "$SRC_DIR" && \
  find . -type f -print0 | LC_ALL=C sort -z | \
  tar --no-recursion --null -T - \
      --owner=0 --group=0 --numeric-owner --mtime='UTC 1970-01-01' \
      -cf "$ARCHIVE" )

DIGEST="sha256:$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
SIZE="$(wc -c <"$ARCHIVE")"
echo "   digest: $DIGEST"
echo "   size:   $SIZE bytes"

REF="${REPO}:${TAG}"
echo ":: pushing to ${REF}"
( cd "$WORK" && \
  oras push "$REF" \
    --artifact-type application/vnd.praesidio.policy-bundle.v1 \
    "bundle.tar:application/vnd.praesidio.policy-bundle.v1+tar" )

# Resolve immutable digest reference for signing.
RESOLVED="$(oras manifest fetch --descriptor "$REF" 2>/dev/null | \
  sed -n 's/.*"digest":"\([^"]*\)".*/\1/p' | head -n1)"
if [ -z "$RESOLVED" ]; then
  echo "WARNING: could not resolve manifest digest; falling back to tag-only sign" >&2
  SIGN_REF="$REF"
else
  SIGN_REF="${REPO}@${RESOLVED}"
fi

if [ "$SIGN" = "1" ]; then
  echo ":: cosign sign ${SIGN_REF}"
  cosign sign --yes "$SIGN_REF"
else
  echo "   --no-sign: skipping cosign"
fi

cat <<EOF

==============================================================================
Published policy bundle.

  Reference:  ${SIGN_REF}
  Tag:        ${REF}
  Archive:    bundle.tar  (sha256: ${DIGEST#sha256:})

To consume from the gateway:
  PRAESIDIO_POLICY_BUNDLE=oci://${SIGN_REF}

To verify manually (keyless Fulcio):
  cosign verify-blob \\
    --certificate-identity-regexp '.*' \\
    --certificate-oidc-issuer-regexp '.*' \\
    --signature <sig> --certificate <cert> bundle.tar

See docs/operations/signed-bundles.md for the full verification flow.
==============================================================================
EOF
