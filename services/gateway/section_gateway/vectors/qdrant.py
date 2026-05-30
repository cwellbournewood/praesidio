"""Qdrant connector — uses qdrant-client async API or an in-memory mock.

The connector is structured so that tests can substitute an in-memory
client without booting a real Qdrant server. The same code path is used
in production with the real client.
"""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

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
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [((b / 255.0) * 2.0) - 1.0 for b in digest[:16]]


class QdrantClientProtocol(Protocol):
    """Minimal subset of qdrant_client.AsyncQdrantClient used by the connector.

    Defining a Protocol lets us pass a fake in tests without importing
    qdrant_client at all (it's an optional dependency).
    """

    async def upsert(self, collection_name: str, points: list[Any]) -> Any: ...
    async def search(
        self, collection_name: str, query_vector: list[float], limit: int
    ) -> list[Any]: ...
    async def close(self) -> None: ...


class _InMemoryAcl:
    """Process-local ACL backend — useful for dev / tests.

    Production deployments should use the SQL-backed
    ``_AsyncpgAclBackend`` from ``pgvector.py`` (or write one against
    whatever IAM system they already operate).
    """

    def __init__(self) -> None:
        self._allow: dict[str, set[tuple[str | None, str | None]]] = {}

    async def filter_visible(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_groups: list[str],
        document_ids: list[str],
    ) -> set[str]:
        out: set[str] = set()
        for doc_id in document_ids:
            grants = self._allow.get(f"{tenant_id}:{doc_id}", set())
            for pid, grp in grants:
                if pid is not None and pid == principal_id:
                    out.add(doc_id)
                    break
                if grp is not None and grp in principal_groups:
                    out.add(doc_id)
                    break
        return out

    async def grant(
        self,
        *,
        tenant_id: str,
        document_id: str,
        principal_id: str | None = None,
        group: str | None = None,
    ) -> None:
        self._allow.setdefault(f"{tenant_id}:{document_id}", set()).add(
            (principal_id, group)
        )


class QdrantConnector(VectorConnector):
    """qdrant-client implementation of :class:`VectorConnector`."""

    name = "qdrant"

    def __init__(
        self,
        *,
        scanner: DlpScannerProtocol,
        vault: VaultProtocol,
        collection: str,
        client: QdrantClientProtocol | None = None,
        url: str | None = None,
        api_key: str | None = None,
        embed: EmbedFn = _stub_embed,
        acl: AclProtocol | None = None,
        default_ttl_seconds: int = 7 * 24 * 3600,
    ) -> None:
        if client is None:
            if url is None:
                raise ValueError("QdrantConnector requires either `client` or `url`")
            client = self._build_real_client(url=url, api_key=api_key)
        self._client = client
        self._collection = collection
        self._embed = embed
        super().__init__(
            scanner=scanner,
            vault=vault,
            acl=acl or _InMemoryAcl(),
            default_ttl_seconds=default_ttl_seconds,
        )

    @staticmethod
    def _build_real_client(*, url: str, api_key: str | None) -> QdrantClientProtocol:
        try:
            from qdrant_client import AsyncQdrantClient  # type: ignore
        except ImportError as e:  # pragma: no cover - exercised in integration only
            raise RuntimeError(
                "qdrant-client is not installed; add `qdrant-client` to your "
                "deployment image to enable the Qdrant connector"
            ) from e
        return AsyncQdrantClient(url=url, api_key=api_key)  # type: ignore[return-value]

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:  # pragma: no cover
            pass

    async def _persist(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return
        points: list[dict[str, Any]] = []
        for doc in documents:
            vec = await self._embed(doc.text)
            points.append(
                {
                    "id": doc.id,
                    "vector": vec,
                    "payload": {
                        "sanitised_text": doc.text,
                        "metadata": doc.metadata,
                    },
                }
            )
        await self._client.upsert(collection_name=self._collection, points=points)

    async def _raw_query(self, query: str, top_k: int) -> list[VectorQueryResult]:
        vec = await self._embed(query)
        hits = await self._client.search(
            collection_name=self._collection, query_vector=vec, limit=top_k
        )
        out: list[VectorQueryResult] = []
        for h in hits:
            payload = getattr(h, "payload", None) or (
                h.get("payload") if isinstance(h, dict) else {}
            )
            doc_id = getattr(h, "id", None) or (h.get("id") if isinstance(h, dict) else None)
            score = getattr(h, "score", None)
            if score is None and isinstance(h, dict):
                score = h.get("score", 0.0)
            out.append(
                VectorQueryResult(
                    id=str(doc_id),
                    score=float(score or 0.0),
                    text=(payload or {}).get("sanitised_text"),
                    metadata=(payload or {}).get("metadata") or {},
                )
            )
        return out
