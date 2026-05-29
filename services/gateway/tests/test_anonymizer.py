"""Anonymiser round-trip: tokenise → restore via in-memory vault."""
from __future__ import annotations

import pytest

from praesidio_gateway.anonymize.tokenizer import (
    anonymise,
    restore_text,
    restore_with_vault,
)
from praesidio_gateway.anonymize.vault import InMemoryBackend, TokenVault
from praesidio_gateway.dlp.detectors import regex as det_regex
from praesidio_gateway.policy.models import Transform


@pytest.mark.asyncio
async def test_roundtrip_tokenise_email(vault_master_key):
    vault = TokenVault(vault_master_key, InMemoryBackend())
    text = "Email alice@example.com about the invoice."
    findings = await det_regex.detect(text)
    transforms = [Transform(label="pii.email", method="tokenise", scope="request", ttl="1h")]

    res = await anonymise(
        text=text,
        findings=findings,
        transforms=transforms,
        tenant_id="acme",
        request_id="req-1",
        vault=vault,
    )

    assert "alice@example.com" not in res.sanitised
    # Placeholder shape <EMAIL_XXXX>
    assert "<EMAIL_" in res.sanitised

    # Round-trip via the in-memory reversal map
    restored = restore_text(res.sanitised, res.reversal)
    assert "alice@example.com" in restored

    # And round-trip via vault lookups (simulates a different process).
    restored2 = await restore_with_vault(
        res.sanitised, tenant="acme", request_id="req-1", vault=vault
    )
    assert "alice@example.com" in restored2


@pytest.mark.asyncio
async def test_redact_is_irreversible(vault_master_key):
    vault = TokenVault(vault_master_key, InMemoryBackend())
    text = "Card 4242 4242 4242 4242."
    findings = await det_regex.detect(text)
    transforms = [Transform(label="financial.credit_card", method="redact", replacement="[REDACTED_PAN]")]
    res = await anonymise(
        text=text, findings=findings, transforms=transforms,
        tenant_id="acme", request_id="req-2", vault=vault,
    )
    assert "[REDACTED_PAN]" in res.sanitised
    assert "4242" not in res.sanitised


@pytest.mark.asyncio
async def test_same_original_same_placeholder(vault_master_key):
    """Within the same scope, identical originals should produce identical placeholders."""
    vault = TokenVault(vault_master_key, InMemoryBackend())
    text = "alice@example.com and alice@example.com"
    findings = await det_regex.detect(text)
    transforms = [Transform(label="pii.email", method="tokenise", scope="session")]
    res = await anonymise(
        text=text, findings=findings, transforms=transforms,
        tenant_id="acme", request_id="req-3", vault=vault,
    )
    placeholders = [e.placeholder for e in res.reversal.entries]
    assert len(set(placeholders)) == 1, placeholders
