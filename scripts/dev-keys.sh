#!/usr/bin/env bash
# Generate development-quality random values for the Section token vault
# and format-preserving encryption keys.
#
# DEV ONLY — production keys must be created in, and stay in, a KMS / HSM.
#
# Usage:
#   scripts/dev-keys.sh                    # print to stdout
#   scripts/dev-keys.sh > .env.local       # write to a dotenv file
#
# Requires: openssl.

set -eu

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl not found on PATH" >&2
  exit 1
fi

# SECTION_VAULT_KEY: 32 bytes, base64
vault_key=$(openssl rand -base64 32)

# SECTION_FPE_KEY: FF3-1 takes 16, 24, or 32 bytes (we generate 32 = AES-256), hex
fpe_key=$(openssl rand -hex 32)

# SECTION_FPE_TWEAK: 56 bits = 7 bytes for FF3-1, hex
fpe_tweak=$(openssl rand -hex 7)

cat <<EOF
# -----------------------------------------------------------------------------
# DEV ONLY — generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by scripts/dev-keys.sh
# Production keys come from KMS (AWS KMS / GCP KMS / Azure Key Vault / Vault).
# Do NOT commit this file. Rotate frequently.
# -----------------------------------------------------------------------------
SECTION_VAULT_KEY=${vault_key}
SECTION_FPE_KEY=${fpe_key}
SECTION_FPE_TWEAK=${fpe_tweak}
EOF
