"""Secret detector tests."""
from __future__ import annotations

import pytest

from section_gateway.dlp.detectors import secrets as det_secrets


@pytest.mark.asyncio
async def test_aws_access_key():
    f = await det_secrets.detect("export AKIAABCDEFGHIJKLMNOP and go")
    assert any(x.label == "credential.aws_access_key" for x in f)


@pytest.mark.asyncio
async def test_github_pat():
    pat = "ghp_" + "A" * 36
    f = await det_secrets.detect(f"token={pat}")
    assert any(x.label == "credential.github_pat" for x in f)


@pytest.mark.asyncio
async def test_openai_key():
    key = "sk-" + "a" * 30
    f = await det_secrets.detect(f"OPENAI_API_KEY={key}")
    assert any(x.label == "credential.openai_api_key" for x in f)


@pytest.mark.asyncio
async def test_anthropic_key():
    key = "sk-ant-" + "a" * 30
    f = await det_secrets.detect(f"ANTHROPIC_API_KEY={key}")
    assert any(x.label == "credential.anthropic_api_key" for x in f)


@pytest.mark.asyncio
async def test_private_key_header():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAA...\n-----END RSA PRIVATE KEY-----"
    f = await det_secrets.detect(pem)
    assert any(x.label == "credential.private_key" for x in f)


@pytest.mark.asyncio
async def test_generic_entropy_only_above_threshold():
    # Low-entropy long token should NOT match credential.generic_high_entropy.
    f = await det_secrets.detect("a" * 64)
    assert not any(x.label == "credential.generic_high_entropy" for x in f)
