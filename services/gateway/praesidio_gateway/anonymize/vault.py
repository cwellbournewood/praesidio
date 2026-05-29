"""Token vault: Redis-backed, AES-256-GCM, per-tenant derived keys via HKDF.

Layout
  key:   v1:{tenant}:{request_id}:{placeholder}
  value: base64( nonce(12) || ciphertext )

The encryption key per-tenant is HKDF(PRAESIDIO_VAULT_KEY, salt=tenant).
The AAD on every record binds it to ``b"praesidio|<tenant>|<request_id>"`` —
cross-tenant or cross-request decryption fails.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..obs.metrics import VAULT_OPS_TOTAL

_log = logging.getLogger(__name__)


class VaultBackend(Protocol):
    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...
    async def get(self, key: str) -> bytes | None: ...
    async def close(self) -> None: ...


class RedisBackend:
    """Thin async wrapper around redis-py asyncio client."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import from_url

        self._r = from_url(url, decode_responses=False)

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        await self._r.set(key, value, ex=max(1, ttl_seconds))

    async def get(self, key: str) -> bytes | None:
        return await self._r.get(key)

    async def close(self) -> None:
        try:
            await self._r.aclose()
        except Exception:  # pragma: no cover
            pass


class InMemoryBackend:
    """Process-local backend for tests / fail-soft local dev."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, float | None]] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        import time

        async with self._lock:
            self._data[key] = (value, time.time() + ttl_seconds if ttl_seconds else None)

    async def get(self, key: str) -> bytes | None:
        import time

        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            val, exp = entry
            if exp is not None and exp < time.time():
                self._data.pop(key, None)
                return None
            return val

    async def close(self) -> None:
        self._data.clear()


class TokenVault:
    """Encrypted KV store. Wraps a VaultBackend with AES-256-GCM."""

    def __init__(self, master_key: bytes, backend: VaultBackend) -> None:
        if len(master_key) != 32:
            raise ValueError("vault master key must be 32 bytes")
        self._master = master_key
        self._backend = backend
        self._tenant_keys: dict[str, bytes] = {}

    def _derive(self, tenant: str) -> bytes:
        cached = self._tenant_keys.get(tenant)
        if cached:
            return cached
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=tenant.encode(),
            info=b"praesidio-vault-v1",
        ).derive(self._master)
        self._tenant_keys[tenant] = derived
        return derived

    @staticmethod
    def _key(tenant: str, request_id: str, placeholder: str) -> str:
        return f"v1:{tenant}:{request_id}:{placeholder}"

    @staticmethod
    def _aad(tenant: str, request_id: str) -> bytes:
        return b"praesidio|" + tenant.encode() + b"|" + request_id.encode()

    async def put(
        self,
        *,
        tenant: str,
        request_id: str,
        placeholder: str,
        plaintext: str,
        ttl_seconds: int,
    ) -> None:
        key = self._key(tenant, request_id, placeholder)
        aes = AESGCM(self._derive(tenant))
        nonce = os.urandom(12)
        ct = aes.encrypt(nonce, plaintext.encode("utf-8"), self._aad(tenant, request_id))
        try:
            await self._backend.set(key, base64.b64encode(nonce + ct), ttl_seconds)
            VAULT_OPS_TOTAL.labels(op="put", outcome="ok").inc()
        except Exception:
            VAULT_OPS_TOTAL.labels(op="put", outcome="err").inc()
            raise

    async def get(
        self, *, tenant: str, request_id: str, placeholder: str
    ) -> str | None:
        key = self._key(tenant, request_id, placeholder)
        try:
            raw = await self._backend.get(key)
        except Exception:
            VAULT_OPS_TOTAL.labels(op="get", outcome="err").inc()
            raise
        if raw is None:
            VAULT_OPS_TOTAL.labels(op="get", outcome="miss").inc()
            return None
        try:
            blob = base64.b64decode(raw)
            nonce, ct = blob[:12], blob[12:]
            aes = AESGCM(self._derive(tenant))
            pt = aes.decrypt(nonce, ct, self._aad(tenant, request_id))
            VAULT_OPS_TOTAL.labels(op="get", outcome="ok").inc()
            return pt.decode("utf-8")
        except Exception:
            VAULT_OPS_TOTAL.labels(op="get", outcome="err").inc()
            _log.warning("vault decrypt failed for tenant=%s req=%s", tenant, request_id)
            return None

    async def close(self) -> None:
        await self._backend.close()


def build_vault(master_key: bytes, redis_url: str | None) -> TokenVault:
    backend: VaultBackend
    if not redis_url:
        backend = InMemoryBackend()
    else:
        try:
            backend = RedisBackend(redis_url)
        except Exception:
            _log.warning("falling back to in-memory vault backend")
            backend = InMemoryBackend()
    return TokenVault(master_key, backend)
