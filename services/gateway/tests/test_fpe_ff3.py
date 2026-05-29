"""FF3-1 backend tests.

Covers round-trip across the alphabets Praesidio uses in production
(digits-only for PAN-style numbers, uppercase ASCII, alphanumeric for
IBAN bodies), parameter validation (tweak, key size, min_len), and
tweak-sensitivity (changing the tweak MUST change the ciphertext).
"""
from __future__ import annotations

import secrets
import string

import pytest

from praesidio_gateway.anonymize import fpe
from praesidio_gateway.anonymize._ff3 import FF3Cipher

# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("alphabet", "plaintext"),
    [
        (fpe.ALPHABET_DIGITS, "4111111111111111"),    # PAN-style 16 digits
        (fpe.ALPHABET_DIGITS, "0000000099"),          # leading zeros preserved
        (fpe.ALPHABET_DIGITS, "987654321"),
        (fpe.ALPHABET_UPPER, "HELLOWORLDABCDEF"),
        (fpe.ALPHABET_UPPER, "ABCDEFGH"),
        (fpe.ALPHABET_IBAN_BODY, "1234567890ABCDEFGH"),  # IBAN body sample
        (fpe.ALPHABET_IBAN_BODY, "0044BARC20785812345678"),
        (fpe.ALPHABET_BASE36, "helloworld12345abc"),
    ],
)
def test_ff3_round_trip(alphabet: str, plaintext: str) -> None:
    key = secrets.token_bytes(16)
    tweak = b"\xde\xad\xbe\xef\x12\x34\x56"
    ct = fpe.encrypt(key=key, tweak=tweak, alphabet=alphabet, plaintext=plaintext, min_len=2)
    assert len(ct) == len(plaintext)
    assert ct != plaintext  # vanishingly unlikely for these inputs
    rt = fpe.decrypt(key=key, tweak=tweak, alphabet=alphabet, ciphertext=ct, min_len=2)
    assert rt == plaintext


def test_ff3_round_trip_192bit_key() -> None:
    key = secrets.token_bytes(24)
    pt = "1234567890123456"
    ct = fpe.encrypt(
        key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext=pt, min_len=2
    )
    assert fpe.decrypt(
        key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, ciphertext=ct, min_len=2
    ) == pt


def test_ff3_round_trip_256bit_key() -> None:
    key = secrets.token_bytes(32)
    pt = "1234567890123456"
    ct = fpe.encrypt(
        key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext=pt, min_len=2
    )
    assert fpe.decrypt(
        key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, ciphertext=ct, min_len=2
    ) == pt


# ---------------------------------------------------------------------------
# Tweak sensitivity
# ---------------------------------------------------------------------------

def test_changing_tweak_changes_ciphertext() -> None:
    key = secrets.token_bytes(16)
    pt = "1234567890"
    ct1 = fpe.encrypt(
        key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext=pt, min_len=2
    )
    ct2 = fpe.encrypt(
        key=key,
        tweak=b"\x01\x02\x03\x04\x05\x06\x07",
        alphabet=fpe.ALPHABET_DIGITS,
        plaintext=pt,
        min_len=2,
    )
    assert ct1 != ct2


def test_changing_key_changes_ciphertext() -> None:
    pt = "1234567890"
    ct1 = fpe.encrypt(
        key=b"\x00" * 16, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext=pt, min_len=2
    )
    ct2 = fpe.encrypt(
        key=b"\xff" * 16, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext=pt, min_len=2
    )
    assert ct1 != ct2


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_min_len_enforced() -> None:
    key = secrets.token_bytes(16)
    with pytest.raises(ValueError, match="shorter than min length"):
        fpe.encrypt(
            key=key, tweak=b"\x00" * 7, alphabet=fpe.ALPHABET_DIGITS, plaintext="12", min_len=6
        )


def test_rejects_chars_outside_alphabet() -> None:
    key = secrets.token_bytes(16)
    with pytest.raises(ValueError, match="outside the FPE alphabet"):
        fpe.encrypt(
            key=key,
            tweak=b"\x00" * 7,
            alphabet=fpe.ALPHABET_DIGITS,
            plaintext="123abc456",
            min_len=2,
        )


def test_rejects_invalid_key_size() -> None:
    with pytest.raises(ValueError, match="key must be 128/192/256 bits"):
        FF3Cipher(key=b"\x00" * 15, alphabet=fpe.ALPHABET_DIGITS)


def test_rejects_oversize_tweak() -> None:
    key = secrets.token_bytes(16)
    with pytest.raises(ValueError, match="tweak must be at most"):
        fpe.encrypt(
            key=key,
            tweak=b"\x00" * 8,
            alphabet=fpe.ALPHABET_DIGITS,
            plaintext="1234567890",
            min_len=2,
        )


def test_short_tweak_is_left_padded() -> None:
    """A 4-byte tweak should be accepted (left-padded to 7 bytes)."""
    key = secrets.token_bytes(16)
    ct_short = fpe.encrypt(
        key=key,
        tweak=b"\x01\x02\x03\x04",
        alphabet=fpe.ALPHABET_DIGITS,
        plaintext="1234567890",
        min_len=2,
    )
    ct_padded = fpe.encrypt(
        key=key,
        tweak=b"\x00\x00\x00\x01\x02\x03\x04",
        alphabet=fpe.ALPHABET_DIGITS,
        plaintext="1234567890",
        min_len=2,
    )
    assert ct_short == ct_padded


def test_rejects_radix_out_of_range() -> None:
    key = secrets.token_bytes(16)
    with pytest.raises(ValueError, match="radix must be in"):
        FF3Cipher(key=key, alphabet="x")  # radix 1
    with pytest.raises(ValueError, match="radix must be in"):
        FF3Cipher(key=key, alphabet="".join(chr(0x21 + i) for i in range(70)))


def test_rejects_duplicate_alphabet() -> None:
    key = secrets.token_bytes(16)
    with pytest.raises(ValueError, match="unique characters"):
        FF3Cipher(key=key, alphabet="01234567899")  # duplicate '9'


def test_minlen_for_radix() -> None:
    """At radix 10, minlen must be >= 2 (radix^2 = 100 >= 100)."""
    c = FF3Cipher(key=b"\x00" * 16, alphabet=string.digits)
    assert c.minlen == 2
    # At radix 2 minlen must be 7 (2^7 = 128 >= 100).
    c2 = FF3Cipher(key=b"\x00" * 16, alphabet="01")
    assert c2.minlen == 7


def test_maxlen_bound_enforced() -> None:
    key = secrets.token_bytes(16)
    c = FF3Cipher(key=key, alphabet=string.digits)
    too_long = "1" * (c.maxlen + 1)
    with pytest.raises(ValueError, match="maxlen"):
        c.encrypt(too_long, b"\x00" * 7)


def test_is_available() -> None:
    assert fpe.is_available() is True
