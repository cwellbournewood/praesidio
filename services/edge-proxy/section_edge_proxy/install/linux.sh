#!/bin/sh
# Section Edge Proxy — Linux trust-store install.
#
# Usage:
#   sudo /bin/sh linux.sh <cert.crt> [--uninstall]
#
# Copies the cert into the distribution's anchor directory and runs
# the trust-update tool:
#   - Debian / Ubuntu: /usr/local/share/ca-certificates + update-ca-certificates
#   - Fedora / RHEL:    /etc/pki/ca-trust/source/anchors + update-ca-trust
#   - openSUSE:         /etc/pki/trust/anchors + update-ca-certificates
#
# Exit codes:
#   0  success
#   1  invalid arguments
#   2  trust-update failed
#   3  not running as root
#   4  unsupported distribution
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

# Detect distribution by looking for the update tool.
ANCHOR_DIR=""
UPDATE_CMD=""
if command -v update-ca-certificates >/dev/null 2>&1; then
    if [ -d /usr/local/share/ca-certificates ]; then
        ANCHOR_DIR=/usr/local/share/ca-certificates
    elif [ -d /etc/pki/trust/anchors ]; then
        ANCHOR_DIR=/etc/pki/trust/anchors
    fi
    UPDATE_CMD=update-ca-certificates
elif command -v update-ca-trust >/dev/null 2>&1; then
    ANCHOR_DIR=/etc/pki/ca-trust/source/anchors
    UPDATE_CMD="update-ca-trust extract"
fi

if [ -z "$ANCHOR_DIR" ] || [ -z "$UPDATE_CMD" ]; then
    echo "ERROR: Unsupported distribution: no update-ca-certificates or update-ca-trust." >&2
    exit 4
fi

INSTALLED="$ANCHOR_DIR/section-edge-proxy.crt"

if [ "$MODE" = "--uninstall" ]; then
    echo "Removing Section CA from $ANCHOR_DIR..."
    rm -f "$INSTALLED"
    if ! $UPDATE_CMD; then
        echo "ERROR: $UPDATE_CMD failed during uninstall" >&2
        exit 2
    fi
    echo "OK: Section CA removed."
    exit 0
fi

echo "Installing Section CA into $ANCHOR_DIR..."
cp "$CERT" "$INSTALLED"
chmod 0644 "$INSTALLED"
if ! $UPDATE_CMD; then
    echo "ERROR: $UPDATE_CMD failed" >&2
    exit 2
fi
echo "OK: Section CA installed."
exit 0
