# 05 · Anonymisation & Token Vault

## Three transforms, picked per finding

| Method | Reversible | Preserves shape | Use when |
|---|---|---|---|
| **Tokenise** (vault placeholder) | ✅ via vault | ❌ (placeholder unlike original) | Names, IDs, free-text PII — the model only needs a stable referent |
| **FPE** (FF3-1) | ✅ via key | ✅ (same alphabet/length) | Numbers the model may reason about (account numbers, phone) — analytics on shape preserved |
| **Redact** | ❌ | partial (length-preserved) | Hard secrets (API keys), regulated identifiers, anything that must never round-trip |

A policy can mix all three on the same prompt:

```
"Email john.smith@acme.com about invoice 4471 and his card 4242 4242 4242 4242"
                  └────────────┘             └──┘            └────────────────┘
                  tokenise(PERSON)            └ kept          redact(PAN_LUHN)

becomes:
"Email <EMAIL_a1b2>@<ORG_c3d4>.com about invoice 4471 and his card [REDACTED_PAN]"
```

The model produces an answer; on the way back the placeholders are restored
from the vault — the user sees `john.smith@acme.com` again, the model never
did.

## Token vault

Storage: Redis, encrypted at rest with `SECTION_VAULT_KEY` (AES-256-GCM,
per-tenant derived key via HKDF). Schema:

```
key:   v1:{tenant}:{request_id}:{placeholder}
value: ciphertext(original)
TTL:   policy-controlled (default 1h), max 24h
```

The vault is a *reversal cache*, not a permanent record. After TTL the
mapping is gone; if a user later replays an old response, placeholders are
left in. This is intentional and aligns with no-retention guarantees.

### Scopes

- `request` (default) — mapping unique to one request id
- `session` — same mapping reused across a session (so the model sees
  the same `<PERSON_a1b2>` for "John" across turns)
- `tenant` — stable mapping across the whole tenant (rare; only for
  ID-style fields where the same alias must always mean the same thing)

Session and tenant scope make the same entity stable, which makes model
output much more coherent — `<PERSON_a1b2>` consistently means "John".

### Placeholder grammar

```
<LABEL>            – first occurrence in a request
<LABEL_xxxx>       – disambiguated for multiple distinct entities of same label
```

`xxxx` is a 4-char base32 hash of `(tenant, scope_key, original)`. Models tend
to handle these well; we benchmark against
[`docs/benchmarks/anonymisation-utility.md`](../benchmarks/anonymisation-utility.md).

## FPE (FF3-1)

NIST SP 800-38G FF3-1 implementation (see
`services/gateway/section_gateway/anonymize/fpe.py`). Tweak per entity-type
+ tenant; key from `SECTION_FPE_KEY`. Alphabets:

| Entity | Alphabet | Min length |
|---|---|---|
| phone | digits | 7 |
| account number | digits | 6 |
| alpha-id | base36 | 4 |

FPE is enabled per-finding in policy. Reversal is keyed and deterministic, so
it requires no vault round-trip.

## Redaction

Either `[REDACTED]`, `[REDACTED_LABEL]`, or length-preserved bullets
(`••••@••••.com`) — chosen per policy. Length preservation can leak length;
default is label form.

## De-anonymisation

The reversal pass walks the streamed response with a state machine that
tolerates:
- placeholders split across SSE chunks (we buffer up to the longest
  placeholder token),
- the model paraphrasing the placeholder (e.g. `<EMAIL_a1b2>` rendered as
  `EMAIL a1b2`) — handled by a tolerant regex,
- the model inventing new placeholders (ignored, replaced with `[unknown]`),
- the model *not* using the placeholder at all (no-op).

## Failure modes

| Failure | Behaviour |
|---|---|
| Vault unreachable on write | Per-policy `fail_mode`. `closed` blocks. |
| Vault unreachable on read | Response returned with placeholders intact; banner in UI; audit `degraded` |
| TTL expires mid-stream | Same as above |
| FPE key rotation in flight | Old key kept in keyring for `2 × max_ttl` |

## Threats

See [threat-model.md](../threat-model.md#anonymisation). Notable:
- **Inference attack**: stable tenant-scope placeholders can leak set
  membership. Mitigation: per-request scope by default; tenant scope only
  for fields opted-in.
- **Vault compromise**: AES-GCM AAD binds ciphertext to
  `(tenant, request_id)` so cross-tenant decryption fails even with key
  knowledge.
