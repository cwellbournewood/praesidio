# ADR-0002 · Anonymisation strategy

Date: 2026-05-27 · Status: Accepted

## Context

The platform must keep LLM answers useful while removing sensitive content
on the way in. Three credible approaches: irreversible redaction; reversible
tokenisation with a vault; format-preserving encryption (FPE).

## Decision

Support all three, choose per-finding in policy. Default is **vault-backed
reversible tokenisation** for free-text PII because:

- model output quality is dramatically better when the model sees a stable
  referent (`<PERSON_a1b2>`) instead of `[REDACTED]` everywhere,
- restoring placeholders on the way out is invisible to the user and to
  downstream applications.

FPE (FF3-1) is used for shape-sensitive numeric fields (phone, account
number) where the model may reason about length / Luhn / etc.

Redaction is used for hard secrets that must never round-trip.

## Consequences

- ➕ High answer utility.
- ➕ Per-policy flexibility — healthcare can pick stricter modes.
- ➖ Vault must be operated as if it held PII (because, for the TTL window,
  it does). Mitigations in [05-anonymization.md](../architecture/05-anonymization.md).
- ➖ Three implementations to maintain — but each is small.
