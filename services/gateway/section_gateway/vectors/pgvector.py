"""pgvector connector (Postgres + the ``pgvector`` extension).

Uses asyncpg directly so we don't pull SQLAlchemy mapper overhead into
the hot retrieval path. The connector owns three tables (created by
``migrations/200-vector-acl.sql``):

* ``vector_documents``   — (id, tenant_id, sanitised_text, metadata, embedding)
* ``documents_acl``      — (tenant_id, document_id, principal_id?, group?)
* (pgvector's ``vector`` column type comes from the extension)

The embedding strategy is intentionally pluggable via a callable so the
gateway can use the operator's preferred embedding model without
hard-coding any provider. Tests pass a deterministic hash-based stub.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from .base import (
    AclProtocol,
    DlpScannerProtocol,
    VaultProtocol,
    VectorConnector,
    VectorDocument,
    VectorQueryResult,
)

EmbedFn = Callable[[str], Awaitable[list[float]]]


async def _stub_embed(text: str) -> list[float]:
    """Deterministic 16-dim embedding for tests / local dev.

    NOT a real embedding — purely a sha256-derived hash projected into
    [-1, 1]. Good enough for unit tests of the persistence + ACL path
    without dragging in a real model.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [((b / 255.0) * 2.0) - 1.0 for b in digest[:16]]


class _AsyncpgAclBackend:
    """Concrete ACL backend backed by the ``documents_acl`` table."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any | None = None

    async def _connect(self) -> Any:
        if self._pool is None:
            import asyncpg  # local import; only required at runtime

            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
        return self._pool

    async def filter_visible(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_groups: list[str],
        document_ids: list[str],
    ) -> set[str]:
        if not document_ids:
            return set()
        pool = await self._connect()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT document_id
                  FROM documents_acl
                 WHERE tenant_id = $1
                   AND document_id = ANY($2::text[])
                   AND (
                        (principal_id IS NOT NULL AND principal_id = $3)
                        OR (group_name IS NOT NULL AND group_name = ANY($4::text[]))
                       )
                """,
                tenant_id,
                document_ids,
                principal_id,
                principal_groups,
            )
        return {r["document_id"] for r in rows}

    async def grant(
        self,
        *,
        tenant_id: str,
        document_id: str,
        principal_id: str | None = None,
        group: str | None = None,
    ) -> None:
        if principal_id is None and group is None:
            raise ValueError("grant requires principal_id or group")
        pool = await self._connect()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents_acl (tenant_id, document_id, principal_id, group_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
                """,
                tenant_id,
                document_id,
                principal_id,
                group,
            )


class PgVectorConnector(VectorConnector):
    """pgvector implementation of :class:`VectorConnector`."""

    name = "pgvector"

    def __init__(
        self,
        *,
        scanner: DlpScannerProtocol,
        vault: VaultProtocol,
        dsn: str,
        embed: EmbedFn = _stub_embed,
        acl: AclProtocol | None = None,
        dim: int = 16,
        default_ttl_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self._dsn = dsn
        self._embed = embed
        self._dim = dim
        self._pool: Any | None = None
        super().__init__(
            scanner=scanner,
            vault=vault,
            acl=acl or _AsyncpgAclBackend(dsn),
            default_ttl_seconds=default_ttl_seconds,
        )

    async def _pool_get(self) -> Any:
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        backend = getattr(self._acl, "_pool", None)
        if backend is not None:
            await backend.close()

    @staticmethod
    def _vec_literal(vec: list[float]) -> str:
        """Format a python list as a pgvector ``vector`` literal."""
        return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    async def _persist(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return
        pool = await self._pool_get()
        rows = []
        for doc in documents:
            vec = await self._embed(doc.text)
            if len(vec) != self._dim:
                raise ValueError(
                    f"embedding dimension {len(vec)} != configured {self._dim}"
                )
            rows.append(
                (
                    doc.id,
                    doc.metadata.get("section.tenant_id", ""),
                    doc.text,
                    json.dumps(doc.metadata),
                    self._vec_literal(vec),
                )
            )
        async with pool.acquire() as conn:
            # Cast the text literal to vector so callers don't need to
            # know pgvector's binary protocol.
            for r in rows:
                await conn.execute(
                    """
                    INSERT INTO vector_documents
                        (id, tenant_id, sanitised_text, metadata, embedding)
                    VALUES ($1, $2, $3, $4::jsonb, $5::vector)
                    ON CONFLICT (id) DO UPDATE
                       SET sanitised_text = EXCLUDED.sanitised_text,
                           metadata       = EXCLUDED.metadata,
                           embedding      = EXCLUDED.embedding
                    """,
                    *r,
                )

    async def _raw_query(self, query: str, top_k: int) -> list[VectorQueryResult]:
        pool = await self._pool_get()
        vec = await self._embed(query)
        vec_lit = self._vec_literal(vec)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, sanitised_text, metadata,
                       1.0 / (1.0 + (embedding <-> $1::vector)) AS score
                  FROM vector_documents
                 ORDER BY embedding <-> $1::vector
                 LIMIT $2
                """,
                vec_lit,
                top_k,
            )
        out: list[VectorQueryResult] = []
        for r in rows:
            md = r["metadata"]
            if isinstance(md, str):
                md = json.loads(md)
            out.append(
                VectorQueryResult(
                    id=r["id"],
                    score=float(r["score"]),
                    text=r["sanitised_text"],
                    metadata=md or {},
                )
            )
        return out
