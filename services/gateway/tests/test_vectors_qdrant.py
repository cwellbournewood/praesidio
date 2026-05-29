"""QdrantConnector tests — exercised with a Protocol-based in-memory client.

These tests do NOT require a running Qdrant server. The connector accepts
any object that satisfies the ``QdrantClientProtocol`` shape, so we hand
it a tiny dict-backed fake that records upserts and returns canned
search hits. The real ``qdrant_client.AsyncQdrantClient`` path is
exercised in the integration suite, not here.

Covers:

  1. _persist emits points with sanitised text + embedding to the client.
  2. scan_on_write substitutes findings before the points reach the client.
  3. Critical secret findings cause the doc to be blocked, never upserted.
  4. validate_retrieval drops hits the principal cannot read.
  5. validate_retrieval handles both dict-style and attr-style hit objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

# ---- Fakes ----------------------------------------------------------------


@dataclass
class _FakeFinding:
    label: str
    start: int
    end: int
    confidence: float = 0.9


class _FakeScanner:
    def __init__(self, by_text: dict[str, list[_FakeFinding]] | None = None) -> None:
        self._by_text = by_text or {}

    async def scan(self, text: str):
        return list(self._by_text.get(text, []))


class _MemVault:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], str] = {}

    async def put(self, *, tenant, request_id, placeholder, plaintext, ttl_seconds):
        self.store[(tenant, request_id, placeholder)] = plaintext

    async def get(self, *, tenant, request_id, placeholder):
        return self.store.get((tenant, request_id, placeholder))


@dataclass
class _FakeHit:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class _FakeQdrant:
    """In-memory stand-in for qdrant_client.AsyncQdrantClient.

    Implements just enough of the protocol the connector needs:
    upsert, search, close. Stored points are kept verbatim so tests
    can assert on the exact payload that was persisted.
    """

    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.next_search_hits: list[Any] = []
        self.closed = False

    async def upsert(self, collection_name: str, points: list[Any]) -> None:
        for p in points:
            self.upserts.append(p)

    async def search(
        self, collection_name: str, query_vector: list[float], limit: int
    ) -> list[Any]:
        return list(self.next_search_hits[:limit])

    async def close(self) -> None:
        self.closed = True


# ---- Tests ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_emits_sanitised_points():
    from praesidio_gateway.vectors.base import VectorDocument
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    text = "Reach out to bob@example.com for details."
    scanner = _FakeScanner(
        {text: [_FakeFinding(label="pii.email", start=13, end=28)]}
    )
    vault = _MemVault()
    client = _FakeQdrant()

    conn = QdrantConnector(
        scanner=scanner,
        vault=vault,
        collection="docs",
        client=client,
    )
    res = await conn.scan_on_write(
        [VectorDocument(id="d1", text=text)],
        tenant_id="acme",
        request_id="req-1",
    )
    assert res.blocked_doc_ids == []
    assert len(client.upserts) == 1
    payload = client.upserts[0]["payload"]
    assert "bob@example.com" not in payload["sanitised_text"]
    assert payload["sanitised_text"].startswith("Reach out to <EMAIL_")
    assert payload["metadata"].get("praesidio.tenant_id") == "acme"
    assert payload["metadata"].get("praesidio.placeholder_count") == 1
    # Vault must have recorded the reversal.
    assert any(v == "bob@example.com" for v in vault.store.values())


@pytest.mark.asyncio
async def test_secret_findings_block_upsert():
    from praesidio_gateway.vectors.base import VectorDocument
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    text = "AKIAIOSFODNN7EXAMPLE is our key"
    scanner = _FakeScanner(
        {text: [_FakeFinding(label="secrets.aws", start=0, end=20)]}
    )
    vault = _MemVault()
    client = _FakeQdrant()

    conn = QdrantConnector(
        scanner=scanner, vault=vault, collection="docs", client=client
    )
    res = await conn.scan_on_write(
        [VectorDocument(id="d-secret", text=text)],
        tenant_id="acme",
        request_id="req-2",
    )
    assert res.blocked_doc_ids == ["d-secret"]
    assert client.upserts == []
    assert vault.store == {}


@pytest.mark.asyncio
async def test_validate_retrieval_filters_unowned_docs():
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    scanner = _FakeScanner({})
    vault = _MemVault()
    client = _FakeQdrant()
    client.next_search_hits = [
        _FakeHit(id="doc-allowed", score=0.91,
                 payload={"sanitised_text": "hi", "metadata": {"k": 1}}),
        _FakeHit(id="doc-secret", score=0.81,
                 payload={"sanitised_text": "no", "metadata": {}}),
    ]

    conn = QdrantConnector(
        scanner=scanner, vault=vault, collection="docs", client=client
    )
    # Grant only doc-allowed to principal "alice".
    await conn._acl.grant(
        tenant_id="acme", document_id="doc-allowed", principal_id="alice"
    )

    res = await conn.validate_retrieval(
        "anything",
        tenant_id="acme",
        principal_id="alice",
        principal_groups=[],
        top_k=10,
    )
    assert [a.id for a in res.allowed] == ["doc-allowed"]
    assert res.filtered_ids == ["doc-secret"]
    assert res.reason_by_id["doc-secret"] == "acl:not-visible"


@pytest.mark.asyncio
async def test_validate_retrieval_supports_dict_hits():
    """The connector must cope with hits returned as plain dicts too."""
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    scanner = _FakeScanner({})
    vault = _MemVault()
    client = _FakeQdrant()
    client.next_search_hits = [
        {"id": "doc-dict", "score": 0.7,
         "payload": {"sanitised_text": "from-dict", "metadata": {"x": "y"}}},
    ]

    conn = QdrantConnector(
        scanner=scanner, vault=vault, collection="docs", client=client
    )
    await conn._acl.grant(
        tenant_id="acme", document_id="doc-dict", principal_id="alice"
    )

    res = await conn.validate_retrieval(
        "q",
        tenant_id="acme",
        principal_id="alice",
        principal_groups=[],
        top_k=5,
    )
    assert len(res.allowed) == 1
    assert res.allowed[0].id == "doc-dict"
    assert res.allowed[0].text == "from-dict"
    assert res.allowed[0].metadata == {"x": "y"}


@pytest.mark.asyncio
async def test_close_propagates_to_client():
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    scanner = _FakeScanner({})
    vault = _MemVault()
    client = _FakeQdrant()

    conn = QdrantConnector(
        scanner=scanner, vault=vault, collection="docs", client=client
    )
    await conn.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_constructor_requires_client_or_url():
    """No client + no URL is a configuration error, not a silent default."""
    from praesidio_gateway.vectors.qdrant import QdrantConnector

    with pytest.raises(ValueError):
        QdrantConnector(
            scanner=_FakeScanner({}),
            vault=_MemVault(),
            collection="docs",
        )
