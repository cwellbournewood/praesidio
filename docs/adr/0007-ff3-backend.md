# ADR-0007: FF3-1 format-preserving encryption backend

| Status   | Date       | Deciders                |
|----------|------------|-------------------------|
| Accepted | 2026-05-27 | Section core / Lane G |

## Context

Section supports three anonymisation methods, policy-selectable per entity
label:

1. **`redact`** — replace with a fixed marker (`[REDACTED_EMAIL]`).
2. **`tokenise`** — replace with a vault-backed opaque placeholder
   (`<EMAIL_AB12>`), reversible only via the token vault.
3. **`fpe`** — replace with a format-preserving ciphertext that is itself a
   syntactically-valid value (e.g. a 16-digit ciphertext for a 16-digit PAN).

Method (3) is essential for keeping downstream systems happy when they do
length/checksum validation on the proxied payload. For instance, a model
that performs analytics on credit-card numbers wants to see 16-digit
strings, not `<CCN_AB12>`.

The cipher specified in the architecture is **FF3-1**, the NIST SP 800-38G
Revision 1 format-preserving block cipher mode (the post-Vaudenay
narrowed-tweak form, 56-bit tweak / 8 Feistel rounds / AES-ECB primitive).

Up to v0.1 the gateway shipped only a stub: calling `fpe` would raise
`FPEUnavailable`, and policies fell back to `tokenise`. That is unsafe to
ship in v1.0 — operators expect `method: fpe` to *work*.

## Decision

**Vendor a pure-Python FF3-1 implementation** under
`services/gateway/section_gateway/anonymize/_ff3.py`.

We chose vendoring over a PyPI dependency for the following reasons:

- **Auditable**: a single ~250-line file is reviewable in a security audit.
- **No supply-chain risk**: there is no maintained, widely-vetted FF3-1
  package on PyPI as of 2026-05. (`pyffx` implements FF1 only, with a
  known incorrect tweak handling; `ff3` on PyPI is unmaintained since
  2021 and pre-dates the 56-bit tweak narrowing.)
- **Standards-aligned**: the implementation follows NIST SP 800-38G Rev 1
  directly and was cross-checked against the Capital One FF3 Go reference
  (Apache-2.0) for the byte-order conventions (NUMradix big-endian, the
  AES-of-reversed-block construction, and the Feistel split-length flip).
- **Minimal dependency**: only the `cryptography` package (already
  required) for the raw AES-ECB single-block primitive.

## Implementation

`anonymize/_ff3.py` exposes:

- `FF3Cipher(key, alphabet)` — a configured cipher; round-trip via
  `.encrypt(plaintext, tweak)` / `.decrypt(ciphertext, tweak)`.
- Module-level `encrypt(...)` / `decrypt(...)` matching the previous
  `fpe.py` signature.

`anonymize/fpe.py` is now a thin wrapper that validates input characters,
enforces the operator-supplied `min_len`, and delegates to `_ff3`.

Supported alphabets:

| Constant                 | Radix | Use case                          |
|--------------------------|-------|-----------------------------------|
| `ALPHABET_DIGITS`        | 10    | PAN, SSN, phone numbers           |
| `ALPHABET_UPPER`         | 26    | Drug names, ICD codes, BIC bodies |
| `ALPHABET_IBAN_BODY`     | 36    | IBAN body after country+check     |
| `ALPHABET_BASE36`        | 36    | Generic alphanumeric (lowercase)  |

Any custom alphabet with `2 ≤ radix ≤ 62` is accepted at runtime.

Length bounds per FF3-1:

- `minlen = max(2, ceil(log_radix(100)))`  → 2 for radix 10, 7 for radix 2.
- `maxlen = 2 * floor(log_radix(2^96))`     → 56 for radix 10, 19 for radix 36.

## Cryptographic notes

- **Keys** are derived per-tenant from `SECTION_FPE_KEY` via the HKDF
  pipeline (see `anonymize/vault.py`). The cipher accepts 128, 192 or
  256-bit keys.
- **Tweaks** MUST be exactly 7 bytes (56 bits). The wrapper accepts
  shorter values and left-pads with zeros for ergonomics, but production
  callers should derive a unique tweak per (tenant, label, vault_epoch)
  via `HMAC-SHA256` and pass the first 7 bytes.
- **Determinism**: identical (key, tweak, plaintext) → identical
  ciphertext. This is FPE's deliberate property — and the reason rotating
  the tweak periodically (e.g. on `vault_epoch++` every 24h) is the
  primary mitigation for frequency-analysis attacks.
- **Not constant-time**: the implementation uses arbitrary-precision
  Python ints. Don't expose this primitive directly to an attacker-
  controlled rate.

## Alternatives considered

| Option                       | Verdict                                        |
|------------------------------|------------------------------------------------|
| `pyffx` (FF1)                | Wrong algorithm; FF1 doesn't match RFP spec.   |
| `ff3` PyPI package           | Unmaintained; pre-FF3-1 tweak narrowing.       |
| Rust binding (e.g. `ff3-rs`) | Extra build complexity on Windows / Alpine.    |
| Custom AES-CTR keystream     | Not format-preserving without re-mapping logic.|
| Continue raising `FPEUnavailable` | Leaves `method: fpe` permanently unusable. |

## Consequences

**Positive**

- `method: fpe` is now first-class. Policies can request FPE for any label
  with a regular alphabet (PAN, IBAN body, phone, drug code, …).
- The cipher is fully auditable in-tree; no extra supply-chain trust.
- Backwards compatible: `FPEUnavailable` still exists and is still raised
  on misuse, so existing fallback paths (`tokenise` on FPE failure) keep
  working.

**Negative**

- We are now responsible for the security of our own FF3-1 implementation.
  Mitigations: extensive round-trip tests, alphabet/keysize coverage,
  ADR + comments quoting the spec, planned re-validation against the
  NIST FF3 sample test vectors in a future security audit.

## Validation

22 round-trip / parameter-validation tests in
`tests/test_fpe_ff3.py` cover:

- digits-only, uppercase ASCII, alphanumeric and IBAN-body alphabets;
- 128/192/256-bit keys;
- tweak sensitivity (different tweaks ⇒ different ciphertexts);
- key sensitivity;
- min_len enforcement;
- character-outside-alphabet rejection;
- short-tweak left-padding;
- radix out-of-range rejection;
- duplicate-alphabet rejection;
- maxlen and minlen-for-radix correctness.
