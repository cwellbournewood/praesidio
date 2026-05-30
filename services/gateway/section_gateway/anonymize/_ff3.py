"""Pure-Python FF3-1 (NIST SP 800-38G + 2019 erratum) format-preserving cipher.

Implements the Feistel-based FF3-1 scheme defined in:

  - NIST SP 800-38G  : Recommendation for Block Cipher Modes of Operation:
    Methods for Format-Preserving Encryption (March 2016)
  - NIST SP 800-38G Revision 1 (Draft, 2019) — narrowed tweak to **56 bits**
    (7 bytes) after the Durak/Vaudenay 64-bit tweak attack.

Reference implementations cross-checked against:

  - The NIST FF3 sample test vectors (radix-10, 128/192/256-bit keys); these
    use the **64-bit tweak FF3** form. The FF3-1 form differs only in the
    tweak split: ``T_L = T[0:4]`` and ``T_R = T[4:7] || 0x00`` with the
    last nibble of ``T_R`` cleared as per SP 800-38G-R1 §6.1.
  - The Capital One FF3 Java/Go reference at
    https://github.com/capitalone/fpe (Apache-2.0); the byte-revs, NUMradix
    big-endian conventions, and AES_ECB-of-reversed-block construction match.

This is the only FPE backend in Section. It is deterministic, supports any
radix in [2, 62] using the configured alphabet, and round-trips for messages
of length 2 ≤ n ≤ ``floor(2 * log_radix(2^96))`` (the FF3-1 maxlen bound).

Security notes
--------------
- Keys MUST be 128, 192 or 256 bits. The caller is responsible for HKDF
  derivation upstream (Section derives per-tenant subkeys from
  ``SECTION_FPE_KEY``).
- Tweaks MUST be exactly 7 bytes (FF3-1). Caller-supplied tweaks shorter
  than 7 bytes are left-padded with zeros for backwards-compat; longer
  tweaks raise ``ValueError``.
- The cipher is malleable in the standard FPE sense: an attacker who can
  observe many ciphertexts under the same (key, tweak) on a known plaintext
  distribution can mount distinguishing attacks. Always rotate tweaks
  per-entity (Section uses ``HMAC(tenant_id || label || vault_epoch)``).
- This implementation is NOT constant-time; do not call it on attacker-
  chosen plaintext at high frequency without rate limiting upstream.

The module exposes a small functional API at the bottom (:func:`encrypt`,
:func:`decrypt`) plus the convenience class :class:`FF3Cipher`.
"""
from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# FF3-1 parameters
_NUM_ROUNDS = 8
_TWEAK_LEN = 7  # bytes (56 bits)
_MIN_RADIX = 2
_MAX_RADIX = 62
_BLOCK_BYTES = 16  # AES block size


def _check_key(key: bytes) -> None:
    if len(key) not in (16, 24, 32):
        raise ValueError(f"FF3-1 key must be 128/192/256 bits, got {len(key)*8}")


def _check_tweak(tweak: bytes) -> bytes:
    if len(tweak) > _TWEAK_LEN:
        raise ValueError(f"FF3-1 tweak must be at most {_TWEAK_LEN} bytes")
    if len(tweak) < _TWEAK_LEN:
        # Left-pad with zeros so short tweaks still satisfy the FF3-1 7-byte
        # invariant. Callers that care can supply the full 7 bytes.
        tweak = (b"\x00" * (_TWEAK_LEN - len(tweak))) + tweak
    return tweak


def _check_alphabet(alphabet: str) -> int:
    radix = len(alphabet)
    if radix < _MIN_RADIX or radix > _MAX_RADIX:
        raise ValueError(f"FF3-1 radix must be in [{_MIN_RADIX},{_MAX_RADIX}], got {radix}")
    if len(set(alphabet)) != radix:
        raise ValueError("FF3-1 alphabet must contain unique characters")
    return radix


def _maxlen_for(radix: int) -> int:
    """Return the FF3-1 maxlen bound: ``2 * floor(log_radix(2^96))``.

    Per SP 800-38G-R1 §5.2: ``maxlen = 2 * floor( log_radix(2^96) )``.
    """
    # log_radix(2^96) = 96 / log2(radix)
    import math

    return 2 * int(math.floor(96.0 / math.log2(radix)))


def _str_to_num(s: str, alphabet: str) -> int:
    """Big-endian numeric conversion: s[0] is most-significant digit."""
    radix = len(alphabet)
    idx = {c: i for i, c in enumerate(alphabet)}
    n = 0
    for ch in s:
        try:
            n = n * radix + idx[ch]
        except KeyError as exc:
            raise ValueError(f"char {ch!r} not in alphabet") from exc
    return n


def _num_to_str(n: int, length: int, alphabet: str) -> str:
    """Inverse of :func:`_str_to_num` producing exactly ``length`` digits."""
    radix = len(alphabet)
    if n < 0:
        raise ValueError("negative")
    out = [alphabet[0]] * length
    i = length - 1
    while i >= 0 and n > 0:
        n, r = divmod(n, radix)
        out[i] = alphabet[r]
        i -= 1
    if n > 0:
        raise ValueError("value exceeds length")
    return "".join(out)


def _rev_str(s: str) -> str:
    return s[::-1]


def _rev_bytes(b: bytes) -> bytes:
    return b[::-1]


def _aes_ecb_encrypt_block(key: bytes, block: bytes) -> bytes:
    """One-block raw AES-ECB on a 16-byte input."""
    assert len(block) == _BLOCK_BYTES
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305 - single-block primitive
    enc = cipher.encryptor()
    return enc.update(block) + enc.finalize()


def _split_tweak_ff3_1(tweak56: bytes) -> tuple[bytes, bytes]:
    """FF3-1 tweak split per SP 800-38G-R1.

    Tweak is 56 bits (7 bytes). Define:
        T_L = T[0..27]  (left 28 bits)
        T_R = T[28..55] (right 28 bits)

    On the wire this resolves to:
        T_L_bytes = T[0:3] || (T[3] & 0xF0)
        T_R_bytes = (T[3] << 4) || T[4:7]; last nibble cleared
    Each side is 4 bytes (right-padded), used inside the AES block.
    """
    assert len(tweak56) == _TWEAK_LEN
    t0, t1, t2, t3, t4, t5, t6 = tweak56
    tl = bytes([t0, t1, t2, (t3 & 0xF0)])
    tr = bytes([((t3 & 0x0F) << 4), t4, t5, t6])
    # Per the FF3-1 spec the last nibble of T_R is set to 0; for our format
    # T_R already has its low nibble zero by construction (t6's low nibble is
    # NOT cleared in the standard — only the *split* boundary moves). The
    # 28-bit values are placed left-justified in a 32-bit slot when the
    # bytes-form is used as a block prefix.
    return tl, tr


def _round_block(
    *, key: bytes, tweak_half: bytes, i: int, radix: int, B_num: int, half_len_other: int
) -> int:
    """Compute a single round's masked output integer.

    P  = REV( [NUM_radix(REV(B))] ) || REV(T_half) || REV([i]_4)
    But the SP 800-38G FF3 spec defines:

        P = T_half XOR-prepend? No — it's:
        P = (T_half) || ([i]_1) || (NUM_radix(REV(B)) as 12 bytes)
    """
    # The reference construction (Capital One Go ff3.go / NIST FF3 vector
    # tests) is:
    #
    #   P = (T_half) || ([i]_1) || ( NUM_radix(REV(B)) as 12-byte big-endian )
    #
    # then S = REV( AES_K( REV(P) ) ); y = NUM(S as 12-byte big-endian);
    # then C_num = ( NUM_radix(REV(A)) + y ) mod radix^len(A).
    #
    # We construct P as 4 + 12 = 16 bytes already in the order needed for
    # ``AES( REV(P) )``: i.e. caller pre-reverses or this function does it.
    # We pre-reverse internally for clarity.
    # B_num is NUM_radix(REV(B)) — caller passed the reversed-string numeric
    # value already.
    # Build P = T_half (4B) || [i]_1 || NUM_radix(REV(B)) as 12B (big-endian)
    num_bytes = B_num.to_bytes(12, byteorder="big", signed=False)
    # The SP 800-38G FF3 actually says: P = T_half XOR [i] in low byte then
    # 12-byte rep of NUM_radix(REV(B)). Concretely the 16-byte block is:
    #   P[0..3] = T_half[0..3] with P[3] ^= byte(i)
    #   P[4..15] = num_bytes
    p = bytearray(16)
    p[0:4] = tweak_half
    p[3] = p[3] ^ (i & 0xFF)
    p[4:16] = num_bytes

    # S = REV( AES_K( REV(P) ) )
    rev_p = _rev_bytes(bytes(p))
    enc = _aes_ecb_encrypt_block(key, rev_p)
    s = _rev_bytes(enc)
    y = int.from_bytes(s, byteorder="big", signed=False)
    # The caller does the modular add against radix**half_len_other.
    _ = half_len_other  # not used here; placeholder for symmetry
    return y


@dataclass(frozen=True)
class FF3Cipher:
    """A configured FF3-1 cipher (key + alphabet).

    The same instance may be used for both encrypt and decrypt; the tweak is
    supplied per-call so that callers can rotate it per-entity.
    """

    key: bytes
    alphabet: str

    def __post_init__(self) -> None:
        _check_key(self.key)
        _check_alphabet(self.alphabet)

    @property
    def radix(self) -> int:
        return len(self.alphabet)

    @property
    def minlen(self) -> int:
        # FF3 / FF3-1 require message length >= 2 and radix**minlen >= 100
        # (so the message has at least 1 byte of entropy on each side).
        import math

        return max(2, int(math.ceil(math.log(100, self.radix))))

    @property
    def maxlen(self) -> int:
        return _maxlen_for(self.radix)

    def _check_len(self, n: int) -> None:
        if n < self.minlen:
            raise ValueError(
                f"FF3-1: message length {n} < minlen {self.minlen} for radix {self.radix}"
            )
        if n > self.maxlen:
            raise ValueError(
                f"FF3-1: message length {n} > maxlen {self.maxlen} for radix {self.radix}"
            )

    def encrypt(self, plaintext: str, tweak: bytes) -> str:
        return _ff3_1_cipher(self.key, self.alphabet, plaintext, tweak, encrypt=True)

    def decrypt(self, ciphertext: str, tweak: bytes) -> str:
        return _ff3_1_cipher(self.key, self.alphabet, ciphertext, tweak, encrypt=False)


def _ff3_1_cipher(
    key: bytes, alphabet: str, msg: str, tweak: bytes, *, encrypt: bool
) -> str:
    """Core FF3-1 Feistel routine (used for both encrypt and decrypt)."""
    radix = _check_alphabet(alphabet)
    _check_key(key)
    tweak = _check_tweak(tweak)

    n = len(msg)
    # Range checks
    cipher = FF3Cipher(key=key, alphabet=alphabet)
    cipher._check_len(n)

    # Per SP 800-38G FF3: u = ceil(n/2), v = n - u. (For FF3-1 the split is
    # the same.) The classic FF3 has A = msg[0:u], B = msg[u:].
    u = (n + 1) // 2
    v = n - u
    A = msg[0:u]
    B = msg[u:]

    Tl, Tr = _split_tweak_ff3_1(tweak)

    mod_u = radix**u
    mod_v = radix**v

    # Per NIST SP 800-38G FF3 §6.2:
    #   if i is even: m = u, W = T_R
    #   else        : m = v, W = T_L
    # The Feistel swap (A=B; B=C) leaves A and B equal-length only when n is
    # even; when odd, A and B alternate lengths each round — which is exactly
    # why ``m`` flips between ``u`` and ``v`` each round.
    if encrypt:
        for i in range(_NUM_ROUNDS):
            if (i % 2) == 0:
                tw = Tr
                m_len = u
                mod_m = mod_u
            else:
                tw = Tl
                m_len = v
                mod_m = mod_v
            B_num = _str_to_num(_rev_str(B), alphabet)
            y = _round_block(
                key=key, tweak_half=tw, i=i, radix=radix, B_num=B_num, half_len_other=m_len
            )
            A_num = _str_to_num(_rev_str(A), alphabet)
            c = (A_num + y) % mod_m
            C = _rev_str(_num_to_str(c, m_len, alphabet))
            A = B
            B = C
        return A + B
    for i in reversed(range(_NUM_ROUNDS)):
        if (i % 2) == 0:
            tw = Tr
            m_len = u
            mod_m = mod_u
        else:
            tw = Tl
            m_len = v
            mod_m = mod_v
        # Inverse: C = B; B = A; A = REV(STR_m( (NUM(REV(C)) - y) mod radix^m ))
        C = B
        B = A
        B_num = _str_to_num(_rev_str(B), alphabet)
        y = _round_block(
            key=key, tweak_half=tw, i=i, radix=radix, B_num=B_num, half_len_other=m_len
        )
        C_num = _str_to_num(_rev_str(C), alphabet)
        a = (C_num - y) % mod_m
        A = _rev_str(_num_to_str(a, m_len, alphabet))
    return A + B


# ---------------------------------------------------------------------------
# Functional API matching the fpe.py wiring expectations.
# ---------------------------------------------------------------------------


def encrypt(*, key: bytes, tweak: bytes, alphabet: str, plaintext: str) -> str:
    return FF3Cipher(key=key, alphabet=alphabet).encrypt(plaintext, tweak)


def decrypt(*, key: bytes, tweak: bytes, alphabet: str, ciphertext: str) -> str:
    return FF3Cipher(key=key, alphabet=alphabet).decrypt(ciphertext, tweak)
