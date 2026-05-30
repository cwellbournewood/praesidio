#!/usr/bin/env bash
# Generate CycloneDX SBOMs for the gateway and UI images using Syft.
#
# Output: dist/sbom-gateway.cdx.json
#         dist/sbom-ui.cdx.json
#
# Usage:
#   scripts/sbom.sh                                # uses ghcr.io/section/{gateway,ui}:latest
#   GATEWAY_IMAGE=foo:1.2 UI_IMAGE=bar:1.2 scripts/sbom.sh

set -eu

OUT_DIR="${OUT_DIR:-dist}"
GATEWAY_IMAGE="${GATEWAY_IMAGE:-ghcr.io/section/gateway:latest}"
UI_IMAGE="${UI_IMAGE:-ghcr.io/section/ui:latest}"

if ! command -v syft >/dev/null 2>&1; then
  cat <<'EOF' >&2
syft is not installed.

Install:
  # macOS / Linux (one-liner)
  curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

  # or via Homebrew
  brew install syft

  # or via Go
  go install github.com/anchore/syft/cmd/syft@latest

Then re-run: scripts/sbom.sh
EOF
  exit 0
fi

mkdir -p "$OUT_DIR"

run_syft() {
  image="$1"
  out="$2"
  echo ":: syft ${image} -> ${out}"
  syft "$image" -o cyclonedx-json="$out"
}

run_syft "$GATEWAY_IMAGE" "${OUT_DIR}/sbom-gateway.cdx.json"
run_syft "$UI_IMAGE"      "${OUT_DIR}/sbom-ui.cdx.json"

echo "done. SBOMs in ${OUT_DIR}/"
ls -la "$OUT_DIR"/sbom-*.cdx.json
