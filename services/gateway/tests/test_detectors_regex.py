"""Regex detector tests."""
from __future__ import annotations

import pytest

from praesidio_gateway.dlp.detectors import regex as det_regex


@pytest.mark.asyncio
async def test_email_detection():
    findings = await det_regex.detect("Contact me: alice@example.com please.")
    labels = [f.label for f in findings]
    assert "pii.email" in labels


@pytest.mark.asyncio
async def test_phone_detection():
    findings = await det_regex.detect("Ring +44 20 7946 0958 tomorrow.")
    assert any(f.label == "pii.phone" for f in findings)


@pytest.mark.asyncio
async def test_iban_detection():
    findings = await det_regex.detect("IBAN: GB82WEST12345698765432 — pay there.")
    assert any(f.label == "financial.iban" for f in findings)


@pytest.mark.asyncio
async def test_credit_card_luhn():
    # 4242 … is a well-known test card that passes Luhn.
    findings = await det_regex.detect("Card 4242 4242 4242 4242 exp 12/30.")
    assert any(f.label == "financial.credit_card" for f in findings)


@pytest.mark.asyncio
async def test_credit_card_invalid_luhn_rejected():
    # 1234... fails Luhn — should NOT emit financial.credit_card.
    findings = await det_regex.detect("Card 1234 5678 9012 3456 nope.")
    assert not any(f.label == "financial.credit_card" for f in findings)


@pytest.mark.asyncio
async def test_jwt_detection():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmb28ifQ.signedSignedSigned"
    findings = await det_regex.detect(f"Token: {jwt} use it.")
    assert any(f.label == "credential.jwt" for f in findings)


@pytest.mark.asyncio
async def test_ipv4_uuid_mac():
    findings = await det_regex.detect(
        "host 10.0.0.1 mac 00:11:22:33:44:55 uuid 550e8400-e29b-41d4-a716-446655440000"
    )
    labels = {f.label for f in findings}
    assert {"network.ipv4", "network.mac_address", "infra.uuid"}.issubset(labels)


@pytest.mark.asyncio
async def test_findings_have_text_hash_not_raw():
    """The Finding model must never carry raw text."""
    findings = await det_regex.detect("alice@example.com")
    assert findings
    for f in findings:
        assert len(f.text_hash) == 64
        # Quick sanity: confirm sha256 looks like hex.
        int(f.text_hash, 16)
