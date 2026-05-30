"""Principal id derivation: ``apikey:<first-8-hex-of-sha256(raw_key)>`` (Task 1.4)."""
from __future__ import annotations

import hashlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from section_gateway.auth import api_key_fingerprint, resolve_principal
from section_gateway.config import Settings


def _settings(keys: str = "alpha-secret-1,beta-secret-2") -> Settings:
    return Settings(section_api_keys=keys)


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [],
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


def test_fingerprint_is_eight_hex_chars_of_sha256():
    raw = "alpha-secret-1"
    fp = api_key_fingerprint(raw)
    assert len(fp) == 8
    assert fp == hashlib.sha256(raw.encode()).hexdigest()[:8]
    # All hex characters.
    int(fp, 16)


def test_resolve_principal_user_id_uses_fingerprint():
    s = _settings("alpha-secret-1")
    p = resolve_principal(_request(), s, x_api_key="alpha-secret-1")
    expected_fp = hashlib.sha256(b"alpha-secret-1").hexdigest()[:8]
    assert p.user_id == f"apikey:{expected_fp}"
    # Raw key is never exposed on the principal.
    assert "alpha-secret-1" not in p.user_id
    assert p.raw_claims.get("api_key_fp") == expected_fp


def test_resolve_principal_explicit_x_user_overrides_fingerprint():
    s = _settings("alpha-secret-1")
    p = resolve_principal(_request(), s, x_api_key="alpha-secret-1", x_user="alice@acme")
    assert p.user_id == "alice@acme"


def test_resolve_principal_invalid_key_rejected():
    s = _settings("alpha-secret-1")
    with pytest.raises(HTTPException) as exc:
        resolve_principal(_request(), s, x_api_key="wrong")
    assert exc.value.status_code == 401


def test_fingerprint_different_keys_differ():
    a = api_key_fingerprint("alpha-secret-1")
    b = api_key_fingerprint("beta-secret-2")
    assert a != b
