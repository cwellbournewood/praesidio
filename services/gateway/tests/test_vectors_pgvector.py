"""PgVectorConnector tests.

Skipped automatically unless a real Postgres ``DATABASE_URL_PG`` (or
``PRAESIDIO_PG_DSN``) is configured AND the pgvector extension is
available. Follows the same skip pattern as test_rls_postgres.py so
contributors without a local Postgres can still run the unit suite.

When a backend IS available, exercises:

  1. _persist round-trips a sanitised document and the embedding is queryable.
  2. scan_on_write replaces findings with vault placeholders and persists
     ONLY the sanitised text.
  3. _AsyncpgAclBackend grants + filter_visible work for both
     principal-id grants and group grants.
  4. validate_retrieval filters out documents the principal cannot read.
  5. Secret-bearing documents are blocked, never persisted.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.postgres


def _pg_dsn() -> str | None:
    return os.environ.get("PRAESIDIO_PG_DSN") or os.environ.get("DATABASE_URL_PG")


def _asyncpg_dsn() -> str | None:
    """Convert a SQLAlchemy-style DSN to a plain asyncpg DSN.

    ``postgresql+asyncpg://...`` → ``postgresql://...``. asyncpg's
    ``create_pool`` doesn't understand the ``+asyncpg`` driver suffix.
    """
    dsn = _pg_dsn()
    if dsn is None:
        return None
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


# ---- Fakes ----------------------------------------------------------------


@dataclass
class _FakeFinding:
    """Duck-types ``policy.models.Finding`` for substitution purposes."""

    label: str
    start: int
    end: int
    confidence: float = 0.9


class _FakeScanner:
    """Returns pre-canned findings keyed by exact text match."""

    def __init__(self, by_text: dict[str, list[_FakeFinding]]) -> None:
        self._by_text = by_text

    async def scan(self, text: str):
        return list(self._by_text.get(text, []))


class _MemVault:
    """Dict-backed vault used to assert placeholders persist correctly."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], str] = {}

    async def put(self, *, tenant, request_id, placeholder, plaintext, ttl_seconds):
        self.store[(tenant, request_id, placeholder)] = plaintext

    async def get(self, *, tenant, request_id, placeholder):
        return self.store.get((tenant, request_id, placeholder))


# ---- Schema bootstrap -----------------------------------------------------


async def _ensure_schema(dsn: str) -> None:
    """Create the vector_documents + documents_acl tables for the test run."""
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        # The pgvector extension is required; skip if unavailable.
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as e:  # pragma: no cover
            pytest.skip(f"pgvector extension unavailable: {e}")

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_documents (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                sanitised_text TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding vector(16),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents_acl (
                tenant_id    TEXT NOT NULL,
                document_id  TEXT NOT NULL,
                principal_id TEXT,
                group_name   TEXT,
                granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                granted_by   TEXT
            )
            """
        )
    finally:
        await conn.close()


async def _truncate(dsn: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE vector_documents, documents_acl")
    finally:
        await conn.close()


# ---- Fixtures -------------------------------------------------------------


@pytest.fixture
def dsn() -> str:
    dsn = _asyncpg_dsn()
    if dsn is None:
        pytest.skip("PRAESIDIO_PG_DSN not set — pgvector connector test skipped")
    asyncio.get_event_loop().run_until_complete(_ensure_schema(dsn))
    asyncio.get_event_loop().run_until_complete(_truncate(dsn))
    return dsn


# ---- Tests ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_on_write_persists_sanitised_only(dsn):
    """Findings must be substituted with placeholders before write."""
    from praesidio_gateway.vectors.pgvector import PgVectorConnector

    text = "Email me at alice@example.com please."
    scanner = _FakeScanner(
        {text: [_FakeFinding(label="pii.email", start=12, end=29)]}
    )
    vault = _MemVault()

    conn = PgVectorConnector(scanner=scanner, vault=vault, dsn=dsn)
    try:
        from praesidio_gateway.vectors.base import VectorDocument

        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        res = await conn.scan_on_write(
            [VectorDocument(id=doc_id, text=text, metadata={"src": "unit"})],
            tenant_id="acme",
            request_id="req-1",
        )
        assert res.blocked_doc_ids == []
        assert len(res.documents) == 1
        sanitised = res.documents[0].text
        assert "alice@example.com" not in sanitised
        assert sanitised.startswith("Email me at <EMAIL_")
        # The reversal map must have been stored in the vault.
        assert any(v == "alice@example.com" for v in vault.store.values())
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_secret_bearing_documents_are_blocked(dsn):
    """Documents containing labelled secrets must NOT be persisted."""
    from praesidio_gateway.vectors.base import VectorDocument
    from praesidio_gateway.vectors.pgvector import PgVectorConnector

    text = "AWS_KEY=AKIAIOSFODNN7EXAMPLE"
    scanner = _FakeScanner(
        {text: [_FakeFinding(label="secrets.aws", start=8, end=28)]}
    )
    vault = _MemVault()

    conn = PgVectorConnector(scanner=scanner, vault=vault, dsn=dsn)
    try:
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        res = await conn.scan_on_write(
            [VectorDocument(id=doc_id, text=text)],
            tenant_id="acme",
            request_id="req-2",
        )
        assert res.blocked_doc_ids == [doc_id]
        assert res.documents == []
        # And nothing should have hit the vault either.
        assert vault.store == {}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_acl_filters_retrieval(dsn):
    """validate_retrieval must drop docs the principal cannot read."""
    from praesidio_gateway.vectors.base import VectorDocument
    from praesidio_gateway.vectors.pgvector import PgVectorConnector

    scanner = _FakeScanner({})
    vault = _MemVault()
    conn = PgVectorConnector(scanner=scanner, vault=vault, dsn=dsn)

    try:
        doc_visible = f"doc-{uuid.uuid4().hex[:8]}"
        doc_hidden = f"doc-{uuid.uuid4().hex[:8]}"
        await conn.scan_on_write(
            [
                VectorDocument(id=doc_visible, text="quarterly sales numbers"),
                VectorDocument(id=doc_hidden, text="executive comp memo"),
            ],
            tenant_id="acme",
            request_id="req-3",
        )

        # Grant only the visible one to our principal.
        await conn._acl.grant(
            tenant_id="acme", document_id=doc_visible, principal_id="alice"
        )

        res = await conn.validate_retrieval(
            "sales", tenant_id="acme", principal_id="alice",
            principal_groups=[], top_k=10,
        )
        allowed_ids = {a.id for a in res.allowed}
        assert doc_visible in allowed_ids
        assert doc_hidden not in allowed_ids
        assert doc_hidden in res.filtered_ids
        assert res.reason_by_id.get(doc_hidden) == "acl:not-visible"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_acl_group_grant_visible_to_member(dsn):
    """A group-level grant must make the doc visible to any member."""
    from praesidio_gateway.vectors.base import VectorDocument
    from praesidio_gateway.vectors.pgvector import PgVectorConnector

    scanner = _FakeScanner({})
    vault = _MemVault()
    conn = PgVectorConnector(scanner=scanner, vault=vault, dsn=dsn)

    try:
        doc = f"doc-{uuid.uuid4().hex[:8]}"
        await conn.scan_on_write(
            [VectorDocument(id=doc, text="team-only doc")],
            tenant_id="acme",
            request_id="req-4",
        )
        await conn._acl.grant(
            tenant_id="acme", document_id=doc, group="data-eng"
        )

        # A non-member sees nothing.
        outsider = await conn.validate_retrieval(
            "team", tenant_id="acme", principal_id="bob",
            principal_groups=["marketing"], top_k=10,
        )
        assert doc not in {a.id for a in outsider.allowed}

        # A member of the granted group does.
        insider = await conn.validate_retrieval(
            "team", tenant_id="acme", principal_id="carol",
            principal_groups=["data-eng"], top_k=10,
        )
        assert doc in {a.id for a in insider.allowed}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_acl_grant_requires_subject(dsn):
    """grant() without a principal or group is a programming error."""
    from praesidio_gateway.vectors.pgvector import _AsyncpgAclBackend

    backend = _AsyncpgAclBackend(dsn)
    with pytest.raises(ValueError):
        await backend.grant(tenant_id="acme", document_id="x")
