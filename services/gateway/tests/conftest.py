"""Shared fixtures."""
from __future__ import annotations

import os
import secrets

import pytest

os.environ.setdefault("PRAESIDIO_ENV", "development")
os.environ.setdefault("PRAESIDIO_VAULT_KEY", "")
os.environ.setdefault("PRAESIDIO_FPE_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")  # forces in-memory vault backend


@pytest.fixture
def vault_master_key() -> bytes:
    return secrets.token_bytes(32)
