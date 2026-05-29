"""Format-Preserving Encryption (FF3-1, NIST SP 800-38G Rev 1).

This module is the public FPE interface used by the anonymiser. The actual
Feistel implementation lives in :mod:`praesidio_gateway.anonymize._ff3` —
a vetted, pure-Python implementation that depends only on ``cryptography``
(AES-ECB single-block primitive).

See `docs/adr/0007-ff3-backend.md` for the rationale, the cross-checked
reference implementations, and the threat model.
"""
from __future__ import annotations

import logging
import string

from . import _ff3

_log = logging.getLogger(__name__)


class FPEUnavailable(RuntimeError):
    """Raised when no FF3-1 backend is wired in.

    Kept for backwards-compatibility with policy fallback paths. The
    pure-Python backend is always available now, so this is raised only
    on input that the backend itself cannot represent (e.g. unknown key
    size) — and even then the caller can opt to fall back to tokenise.
    """


# Alphabet helpers (NIST SP 800-38G defines radix 2..62).
ALPHABET_DIGITS = string.digits
ALPHABET_BASE36 = string.digits + string.ascii_lowercase
ALPHABET_UPPER = string.ascii_uppercase
# IBAN-body alphabet: digits + uppercase letters (used by SWIFT for the BBAN
# portion after the 2-letter country code and 2-digit check). FF3-1 cannot
# encrypt the country prefix in place because the checksum constraint isn't
# preserved; we encrypt only the body.
ALPHABET_IBAN_BODY = string.digits + string.ascii_uppercase


def _check_input(s: str, alphabet: str, min_len: int) -> None:
    if not all(c in alphabet for c in s):
        raise ValueError("input contains characters outside the FPE alphabet")
    if len(s) < min_len:
        raise ValueError(f"input shorter than min length {min_len}")


def is_available() -> bool:
    """Always True now that the pure-Python backend is bundled."""
    return True


def encrypt(*, key: bytes, tweak: bytes, alphabet: str, plaintext: str, min_len: int = 6) -> str:
    """FF3-1 encrypt over the supplied alphabet.

    Parameters
    ----------
    key:
        AES key, 128/192/256 bits.
    tweak:
        Up to 7 bytes. Shorter values are zero-padded on the left.
    alphabet:
        Characters making up the radix. Length must be in [2, 62].
    plaintext:
        Input string; every character must be in ``alphabet``.
    min_len:
        Defensive lower bound enforced before delegating to the cipher
        (the cipher itself enforces the FF3-1 minlen for radix).
    """
    _check_input(plaintext, alphabet, min_len)
    try:
        return _ff3.encrypt(key=key, tweak=tweak, alphabet=alphabet, plaintext=plaintext)
    except ValueError:
        # Surface input/length errors verbatim — they're user-actionable.
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise FPEUnavailable(f"FF3-1 backend failed: {exc}") from exc


def decrypt(*, key: bytes, tweak: bytes, alphabet: str, ciphertext: str, min_len: int = 6) -> str:
    _check_input(ciphertext, alphabet, min_len)
    try:
        return _ff3.decrypt(key=key, tweak=tweak, alphabet=alphabet, ciphertext=ciphertext)
    except ValueError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise FPEUnavailable(f"FF3-1 backend failed: {exc}") from exc
