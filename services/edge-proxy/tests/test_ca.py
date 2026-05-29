"""Tests for the per-machine CA generation module."""
from __future__ import annotations

import os
import stat

import pytest
from cryptography import x509

from praesidio_edge_proxy import ca


def test_ensure_ca_generates_root_and_key(tmp_ca_dir):
    """First call creates a 4096-bit RSA root cert and writes both files."""
    cert_path, key_path = ca.ensure_ca(tmp_ca_dir)

    assert cert_path.exists()
    assert key_path.exists()

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    # Subject CN must mention Praesidio.
    cns = [
        attr.value
        for attr in cert.subject
        if attr.oid == x509.NameOID.COMMON_NAME
    ]
    assert any("Praesidio" in c for c in cns)

    # Basic constraints: CA true, path length 0.
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert bc.ca is True

    # Public key is 4096-bit RSA.
    pub = cert.public_key()
    assert pub.key_size == 4096


def test_ensure_ca_is_idempotent(tmp_ca_dir):
    """Calling twice reuses the existing CA (same serial number)."""
    cert_path, _ = ca.ensure_ca(tmp_ca_dir)
    serial1 = x509.load_pem_x509_certificate(cert_path.read_bytes()).serial_number

    cert_path2, _ = ca.ensure_ca(tmp_ca_dir)
    serial2 = x509.load_pem_x509_certificate(cert_path2.read_bytes()).serial_number

    assert serial1 == serial2


def test_ensure_ca_force_regenerates(tmp_ca_dir):
    """`force=True` mints a brand new root with a different serial."""
    cert_path, _ = ca.ensure_ca(tmp_ca_dir)
    serial1 = x509.load_pem_x509_certificate(cert_path.read_bytes()).serial_number

    cert_path2, _ = ca.ensure_ca(tmp_ca_dir, force=True)
    serial2 = x509.load_pem_x509_certificate(cert_path2.read_bytes()).serial_number

    assert serial1 != serial2


@pytest.mark.skipif(os.name == "nt", reason="POSIX file-mode check")
def test_private_key_is_user_only(tmp_ca_dir):
    """On POSIX the key file is mode 0600 (owner read/write only)."""
    _, key_path = ca.ensure_ca(tmp_ca_dir)
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    assert mode == 0o600


def test_load_ca_round_trips(tmp_ca_dir):
    """load_ca returns the same cert and key we wrote."""
    cert_path, _ = ca.ensure_ca(tmp_ca_dir)
    cert, key = ca.load_ca(tmp_ca_dir)

    assert key.key_size == 4096
    expected = x509.load_pem_x509_certificate(cert_path.read_bytes())
    assert cert.serial_number == expected.serial_number


def test_load_ca_raises_when_missing(tmp_ca_dir):
    with pytest.raises(FileNotFoundError):
        ca.load_ca(tmp_ca_dir)


def test_remove_ca_deletes_all_files(tmp_ca_dir):
    cert_path, key_path = ca.ensure_ca(tmp_ca_dir)
    combined = cert_path.with_suffix(".pem")
    assert cert_path.exists() and key_path.exists() and combined.exists()

    ca.remove_ca(tmp_ca_dir)

    assert not cert_path.exists()
    assert not key_path.exists()
    assert not combined.exists()


def test_install_command_returns_per_os_script(tmp_ca_dir):
    """The install_command builder returns argv pointing at a real bundled script."""
    ca.ensure_ca(tmp_ca_dir)
    argv, script = ca.install_command(tmp_ca_dir)
    assert script.exists()
    assert isinstance(argv, list) and len(argv) >= 2


def test_uninstall_command_includes_uninstall_flag(tmp_ca_dir):
    ca.ensure_ca(tmp_ca_dir)
    argv, _ = ca.uninstall_command(tmp_ca_dir)
    assert "--uninstall" in argv


def test_default_ca_dir_is_per_os(monkeypatch):
    """Default dir respects $LOCALAPPDATA / Library / XDG_DATA_HOME conventions."""
    monkeypatch.setenv("LOCALAPPDATA", r"C:\fake\local")
    monkeypatch.setenv("XDG_DATA_HOME", "/fake/xdg")
    # Just make sure it's a Path and contains 'Praesidio' or 'praesidio'.
    p = ca.default_ca_dir()
    assert "Praesidio" in str(p) or "praesidio" in str(p)
