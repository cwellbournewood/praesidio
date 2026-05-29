#!/bin/sh
# Praesidio Edge Proxy — macOS trust-store install.
#
# Usage:
#   sudo /bin/sh macos.sh <cert.crt> [--uninstall]
#
# Adds (or removes) the supplied root certificate to the System
# keychain as a trusted root for SSL using `security
# add-trusted-cert`. Requires sudo because /Library/Keychains/
# System.keychain is admin-owned.
#
# Exit codes:
#   0  success
#   1  invalid arguments
#   2  security(8) failed
#   3  not running as root
set -eu

CERT="${1:-}"
MODE="${2:-install}"

if [ -z "$CERT" ] || [ ! -f "$CERT" ]; then
    echo "ERROR: Cert file not found: $CERT" >&2
    exit 1
fi

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: This script must be run as root (use sudo)." >&2
    exit 3
fi

KEYCHAIN="/Library/Keychains/System.keychain"

if [ "$MODE" = "--uninstall" ]; then
    echo "Removing Praesidio CA from System keychain..."
    # `security delete-certificate` matches by CN. Fall back to OK if
    # no matching cert exists.
    security delete-certificate -c "Praesidio Edge Proxy Local CA" "$KEYCHAIN" 2>/dev/null || true
    echo "OK: Praesidio CA removed."
    exit 0
fi

echo "Installing Praesidio CA into System keychain..."
if security add-trusted-cert \
    -d \
    -r trustRoot \
    -k "$KEYCHAIN" \
    "$CERT"
then
    echo "OK: Praesidio CA installed."
    exit 0
else
    rc=$?
    echo "ERROR: security add-trusted-cert failed (exit $rc)" >&2
    exit 2
fi
