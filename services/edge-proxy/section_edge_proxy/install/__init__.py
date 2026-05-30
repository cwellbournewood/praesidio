"""Per-OS trust-store install/uninstall helper scripts.

The Python CLI shells out to one of:

* ``windows.ps1`` — uses ``certutil -addstore -f Root``.
* ``macos.sh`` — uses ``security add-trusted-cert``.
* ``linux.sh`` — copies into ``/usr/local/share/ca-certificates`` (Debian)
  or ``/etc/pki/ca-trust/source/anchors`` (Fedora) then runs the
  distribution's trust-update tool.

Each script accepts the cert path as its first arg, and a literal
``--uninstall`` flag as its second to remove.

These scripts are shipped under the wheel's ``share/`` data dir so
operators can also invoke them by hand (the path is printed by
``section-edge-proxy install-ca``).
"""
