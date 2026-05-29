"""Per-machine root CA generation and management.

The edge proxy MUST mint its own CA on first install rather than ship a
shared one — a shared CA is an enterprise-fleet master key and a
disaster waiting to happen. Each operator machine gets its own 4096-bit
RSA root, valid for ten years, stored under the per-OS application-data
dir with permission 0600 on the private key.

Layout under the CA dir:

```
ca/
├── praesidio-ca.crt    # public root cert; safe to install in trust store
├── praesidio-ca.key    # PRIVATE key — never shipped, never logged
└── leaves/             # cached per-host leaf certs minted by mitmproxy
```

mitmproxy itself handles the leaf-minting machinery once it sees the
root key/cert in its CA-dir layout. We provide:

* :func:`ensure_ca` — create the root if missing and return the
  ``(cert_path, key_path)`` pair.
* :func:`load_ca` — load existing (cert, key) so callers can re-export.
* :func:`install_command` — return the per-OS shell command + script
  path used by :mod:`praesidio_edge_proxy.cli` to add the root to the
  trust store.
* :func:`uninstall_command` — inverse.
"""
from __future__ import annotations

import os
import platform
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

log = structlog.get_logger(__name__)


# --- Paths -----------------------------------------------------------------

def default_ca_dir() -> Path:
    """Return the per-OS application-data dir for the CA bundle.

    * Windows: ``%LOCALAPPDATA%\\Praesidio``
    * macOS: ``~/Library/Application Support/Praesidio``
    * Linux: ``$XDG_DATA_HOME/praesidio`` (falls back to ``~/.local/share/praesidio``)
    """
    sysname = platform.system()
    if sysname == "Windows":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "Praesidio"
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Praesidio"
    # Linux & everyone else.
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "praesidio"


def ca_paths(ca_dir: Path | None = None) -> tuple[Path, Path]:
    """Return ``(cert_path, key_path)`` under *ca_dir* (default per-OS)."""
    base = ca_dir or default_ca_dir()
    return base / "praesidio-ca.crt", base / "praesidio-ca.key"


# --- Generation ------------------------------------------------------------

_KEY_SIZE_BITS = 4096
_VALID_DAYS = 365 * 10
_CN = "Praesidio Edge Proxy Local CA"
_ORG = "Praesidio"


def _generate_keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=_KEY_SIZE_BITS)


def _build_root_cert(key: rsa.RSAPrivateKey, machine_id: str | None = None) -> x509.Certificate:
    """Build the self-signed root certificate.

    *machine_id*, when provided, is encoded into the subject CN so a
    rebuilt CA on the same machine is distinguishable from a fresh one
    in trust-store listings.
    """
    cn = _CN
    if machine_id:
        cn = f"{_CN} ({machine_id})"

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, _ORG),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Edge Proxy"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )

    not_before = datetime.now(UTC) - timedelta(minutes=5)
    not_after = not_before + timedelta(days=_VALID_DAYS)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
    )
    return builder.sign(private_key=key, algorithm=hashes.SHA256())


def _write_secret(path: Path, data: bytes) -> None:
    """Write *data* to *path* with 0600 permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Open with O_CREAT|O_WRONLY|O_TRUNC + mode 0600 so the file is
    # never world-readable between create and chmod (TOCTOU-safe).
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    mode = stat.S_IRUSR | stat.S_IWUSR  # 0600
    fd = os.open(str(path), flags, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        # On Windows the umask trick doesn't enforce 0600 but the file
        # still lives under %LOCALAPPDATA% which is user-only by ACL.
        raise
    # On POSIX, double-check the mode survived.
    if os.name == "posix":
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass


def _write_public(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def ensure_ca(ca_dir: Path | None = None, *, force: bool = False) -> tuple[Path, Path]:
    """Generate the CA if missing and return ``(cert_path, key_path)``.

    Idempotent — calling twice on the same machine reuses the existing
    pair unless ``force=True``. Never logs the private key.

    Args:
        ca_dir: Optional override directory. Defaults to the per-OS
            application-data location.
        force: When true, regenerate even if a CA already exists.
            **Will break TLS for any cert previously minted from the
            old root** — use only when the old key is compromised.
    """
    cert_path, key_path = ca_paths(ca_dir)
    if cert_path.exists() and key_path.exists() and not force:
        log.info("ca.reuse_existing", cert=str(cert_path))
        return cert_path, key_path

    log.info("ca.generate", cert=str(cert_path))
    key = _generate_keypair()
    cert = _build_root_cert(key)

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    _write_public(cert_path, cert_pem)
    _write_secret(key_path, key_pem)

    # mitmproxy also wants a combined PEM. Write it next to the cert
    # so `--certs *=...` can pick it up when we boot.
    combined = key_pem + cert_pem
    combined_path = cert_path.with_suffix(".pem")
    _write_secret(combined_path, combined)

    return cert_path, key_path


def load_ca(ca_dir: Path | None = None) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Load an existing CA from disk.

    Raises:
        FileNotFoundError: if either the cert or key is missing.
    """
    cert_path, key_path = ca_paths(ca_dir)
    if not cert_path.exists():
        raise FileNotFoundError(f"CA cert not found at {cert_path}")
    if not key_path.exists():
        raise FileNotFoundError(f"CA key not found at {key_path}")

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("CA key is not an RSA private key")
    return cert, key


def remove_ca(ca_dir: Path | None = None) -> None:
    """Delete the on-disk CA. The trust-store entry is removed separately."""
    cert_path, key_path = ca_paths(ca_dir)
    combined = cert_path.with_suffix(".pem")
    for p in (combined, key_path, cert_path):
        try:
            p.unlink()
            log.info("ca.removed", path=str(p))
        except FileNotFoundError:
            continue


# --- Install / uninstall scripts -------------------------------------------

_INSTALL_SCRIPTS = {
    "Windows": "windows.ps1",
    "Darwin": "macos.sh",
    "Linux": "linux.sh",
}


def install_command(ca_dir: Path | None = None) -> tuple[list[str], Path]:
    """Return ``(argv, script_path)`` to install the CA on the current OS.

    The script path is shipped with the package; we pass the cert path
    as its first arg. Caller invokes via ``subprocess.run`` with elevated
    privileges (Windows admin / sudo on POSIX) — the helper script
    surfaces clear errors when run unprivileged.
    """
    cert_path, _ = ca_paths(ca_dir)
    script_name = _INSTALL_SCRIPTS.get(platform.system())
    if script_name is None:
        raise RuntimeError(f"Unsupported OS: {platform.system()}")
    script_path = Path(__file__).parent / "install" / script_name
    if platform.system() == "Windows":
        argv = [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            str(cert_path),
        ]
    else:
        argv = ["/bin/sh", str(script_path), str(cert_path)]
    return argv, script_path


def uninstall_command(ca_dir: Path | None = None) -> tuple[list[str], Path]:
    """Return ``(argv, script_path)`` to uninstall the CA on the current OS.

    Uses the same script with an ``--uninstall`` arg; the scripts branch
    on that flag.
    """
    cert_path, _ = ca_paths(ca_dir)
    script_name = _INSTALL_SCRIPTS.get(platform.system())
    if script_name is None:
        raise RuntimeError(f"Unsupported OS: {platform.system()}")
    script_path = Path(__file__).parent / "install" / script_name
    if platform.system() == "Windows":
        argv = [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            str(cert_path),
            "--uninstall",
        ]
    else:
        argv = ["/bin/sh", str(script_path), str(cert_path), "--uninstall"]
    return argv, script_path


__all__ = [
    "default_ca_dir",
    "ca_paths",
    "ensure_ca",
    "load_ca",
    "remove_ca",
    "install_command",
    "uninstall_command",
]
