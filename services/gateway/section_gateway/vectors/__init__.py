"""Vector-store connectors with DLP at embedding-write and retrieval-read.

Two seams that vector stores create for sensitive data leakage:

1. **Write-time** — documents are run through an embedding model and the
   raw text is persisted in the store alongside the vector. Sensitive
   entities (PII, secrets, credentials) end up encoded in the embeddings
   AND retained verbatim in metadata. Section's :meth:`VectorConnector.
   scan_on_write` hooks the DLP pipeline before the document is stored,
   replacing sensitive spans with reversible vault placeholders and
   persisting the reversal map keyed by ``document_id``.

2. **Read-time** — semantic search returns documents the calling
   principal may not have permission to read. The classic "I asked about
   topic X and the model surfaced HR record Y" failure mode. Section's
   :meth:`VectorConnector.validate_retrieval` consults a
   ``documents_acl`` table and filters the result set to documents the
   principal owns or has been explicitly granted access to.

Two concrete connectors ship:

* :class:`section_gateway.vectors.pgvector.PgVectorConnector` — uses
  asyncpg directly. Suitable for self-hosted Postgres + ``pgvector``.
* :class:`section_gateway.vectors.qdrant.QdrantConnector` — uses
  ``qdrant-client`` async API. Suitable for the hosted Qdrant Cloud or
  a self-hosted deployment.

Both implement the same abstract base so additional stores (Pinecone,
Weaviate, Milvus, ...) can plug in without touching policy code.
"""
from __future__ import annotations

from .base import (
    AllowedDocument,
    AllowlistedResults,
    ScanResult,
    VectorConnector,
    VectorDocument,
    VectorQueryResult,
)

__all__ = [
    "AllowedDocument",
    "AllowlistedResults",
    "ScanResult",
    "VectorConnector",
    "VectorDocument",
    "VectorQueryResult",
]
