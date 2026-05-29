"""Abstract base for vector-store connectors.

The base class is intentionally small. Each concrete connector owns its
embedding strategy and storage layout — the contract Praesidio enforces
is only:

* every write goes through :meth:`scan_on_write` so DLP runs on the raw
  text BEFORE embedding (so the embedding itself is over the sanitised
  text and the originals never reach the vector store);
* every read goes through :meth:`validate_retrieval` so an ACL filter is
  applied to the result set before the documents leave the gateway.

The base also provides shared helpers for placeholder substitution and
tenant-scoped vault put/get so each concrete connector doesn't reinvent
the wheel.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..dlp.types import Finding

# Re-used vault placeholder grammar — must match
# ``praesidio_gateway.anonymize.tokenizer._PLACEHOLDER_RE`` exactly so
# downstream restore logic works without bespoke regexes per connector.
PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4,8})>")


# ---------------------------------------------------------------------------
# Wire dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VectorDocument:
    """A document presented to a vector store for upsert."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Outcome of :meth:`VectorConnector.scan_on_write`.

    ``documents`` is the post-DLP form (placeholders substituted) that
    will actually be persisted; ``findings_by_doc`` lets the caller
    audit which document tripped which detector.
    """

    documents: list[VectorDocument]
    findings_by_doc: dict[str, list[Finding]] = field(default_factory=dict)
    placeholders_by_doc: dict[str, list[str]] = field(default_factory=dict)
    blocked_doc_ids: list[str] = field(default_factory=list)


@dataclass
class VectorQueryResult:
    """A raw result from the underlying vector store."""

    id: str
    score: float
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AllowedDocument:
    """A query result that passed the ACL filter."""

    id: str
    score: float
    text: str | None
    metadata: dict[str, Any]


@dataclass
class AllowlistedResults:
    """The post-ACL view of a vector query."""

    allowed: list[AllowedDocument]
    filtered_ids: list[str] = field(default_factory=list)
    reason_by_id: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DLP + Vault dependency surface (Protocols so tests can hand in fakes)
# ---------------------------------------------------------------------------


class DlpScannerProtocol(Protocol):
    """Anything that can return Findings for a piece of text.

    Matches ``dlp.pipeline.run`` closely enough that the real pipeline
    can be passed straight in; tests use a hand-rolled fake.
    """

    async def scan(self, text: str) -> list[Finding]: ...


class VaultProtocol(Protocol):
    async def put(
        self,
        *,
        tenant: str,
        request_id: str,
        placeholder: str,
        plaintext: str,
        ttl_seconds: int,
    ) -> None: ...

    async def get(
        self, *, tenant: str, request_id: str, placeholder: str
    ) -> str | None: ...


class AclProtocol(Protocol):
    """Document-level access-control list."""

    async def filter_visible(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_groups: list[str],
        document_ids: list[str],
    ) -> set[str]: ...

    async def grant(
        self,
        *,
        tenant_id: str,
        document_id: str,
        principal_id: str | None = None,
        group: str | None = None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Connector base
# ---------------------------------------------------------------------------


def _label_short(label: str) -> str:
    """Mirror of ``tokenizer._label_short`` — kept local to avoid an import cycle."""
    return label.split(".", 1)[-1].upper().replace(".", "_")


def _placeholder(label: str, scope_key: str, original: str) -> str:
    """Mirror of ``tokenizer._placeholder`` (4-char base32 of (scope|original))."""
    import base64

    short = _label_short(label)
    digest = hashlib.sha256(f"{scope_key}|{original}".encode()).digest()
    suffix = base64.b32encode(digest)[:4].decode("ascii").upper()
    return f"<{short}_{suffix}>"


class VectorConnector:
    """Abstract base. Concrete subclasses must implement the four primitives.

    Subclasses inherit shared helpers for DLP-driven placeholder
    substitution and ACL bookkeeping. The store-specific work
    (embedding, upserting, querying) lives in the subclass.
    """

    name: str = "abstract"

    def __init__(
        self,
        *,
        scanner: DlpScannerProtocol,
        vault: VaultProtocol,
        acl: AclProtocol,
        default_ttl_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self._scanner = scanner
        self._vault = vault
        self._acl = acl
        self._default_ttl = default_ttl_seconds

    # ---- store-specific (override in subclasses) ----

    async def _persist(self, documents: list[VectorDocument]) -> None:  # pragma: no cover
        raise NotImplementedError

    async def _raw_query(self, query: str, top_k: int) -> list[VectorQueryResult]:  # pragma: no cover
        raise NotImplementedError

    # ---- shared DLP + ACL flow ----

    async def scan_on_write(
        self,
        documents: list[VectorDocument],
        *,
        tenant_id: str,
        request_id: str,
        block_on: tuple[str, ...] = ("secrets.aws", "secrets.gcp", "secrets.azure", "credential.generic_high_entropy"),
    ) -> ScanResult:
        """Run DLP over each document, substitute placeholders, persist.

        Documents that contain any label in ``block_on`` are NOT persisted
        — their ids are returned in :attr:`ScanResult.blocked_doc_ids` so
        the caller can produce a useful error response.
        """
        out_docs: list[VectorDocument] = []
        findings_by_doc: dict[str, list[Finding]] = {}
        placeholders_by_doc: dict[str, list[str]] = {}
        blocked: list[str] = []

        for doc in documents:
            findings = await self._scanner.scan(doc.text)
            findings_by_doc[doc.id] = findings
            # Block on critical labels.
            if any(f.label in block_on for f in findings):
                blocked.append(doc.id)
                continue
            sanitised, placeholders = await self._substitute(
                text=doc.text,
                findings=findings,
                tenant_id=tenant_id,
                request_id=request_id,
                document_id=doc.id,
            )
            placeholders_by_doc[doc.id] = placeholders
            out_docs.append(
                VectorDocument(
                    id=doc.id,
                    text=sanitised,
                    metadata={
                        **doc.metadata,
                        "praesidio.tenant_id": tenant_id,
                        "praesidio.placeholder_count": len(placeholders),
                    },
                )
            )

        if out_docs:
            await self._persist(out_docs)

        return ScanResult(
            documents=out_docs,
            findings_by_doc=findings_by_doc,
            placeholders_by_doc=placeholders_by_doc,
            blocked_doc_ids=blocked,
        )

    async def _substitute(
        self,
        *,
        text: str,
        findings: list[Finding],
        tenant_id: str,
        request_id: str,
        document_id: str,
    ) -> tuple[str, list[str]]:
        """Replace each finding span with a vault-backed placeholder."""
        if not findings:
            return text, []
        # Greedy left-to-right; drop overlaps.
        ordered = sorted(findings, key=lambda f: (f.start, -f.end))
        chosen: list[Finding] = []
        cursor = 0
        for f in ordered:
            if f.start < cursor:
                continue
            chosen.append(f)
            cursor = f.end

        out_parts: list[str] = []
        pos = 0
        placeholders: list[str] = []
        scope_key = f"doc:{tenant_id}:{document_id}"
        for f in chosen:
            if pos < f.start:
                out_parts.append(text[pos : f.start])
            original = text[f.start : f.end]
            ph = _placeholder(f.label, scope_key, original)
            await self._vault.put(
                tenant=tenant_id,
                request_id=request_id,
                placeholder=ph,
                plaintext=original,
                ttl_seconds=self._default_ttl,
            )
            placeholders.append(ph)
            out_parts.append(ph)
            pos = f.end
        if pos < len(text):
            out_parts.append(text[pos:])
        return "".join(out_parts), placeholders

    async def validate_retrieval(
        self,
        query: str,
        *,
        tenant_id: str,
        principal_id: str,
        principal_groups: list[str],
        top_k: int = 10,
    ) -> AllowlistedResults:
        """Query the store and filter the result set by ACL.

        The query string itself is NOT scanned here — that's the caller's
        responsibility (and is typically already covered by the chat
        DLP pipeline before the embedding even goes out). What we do
        guarantee is that no document the caller is not permitted to
        read leaves the gateway.
        """
        raw = await self._raw_query(query, top_k=top_k)
        if not raw:
            return AllowlistedResults(allowed=[])
        ids = [r.id for r in raw]
        visible = await self._acl.filter_visible(
            tenant_id=tenant_id,
            principal_id=principal_id,
            principal_groups=principal_groups,
            document_ids=ids,
        )
        allowed: list[AllowedDocument] = []
        filtered: list[str] = []
        reasons: dict[str, str] = {}
        for r in raw:
            if r.id in visible:
                allowed.append(
                    AllowedDocument(
                        id=r.id, score=r.score, text=r.text, metadata=r.metadata
                    )
                )
            else:
                filtered.append(r.id)
                reasons[r.id] = "acl:not-visible"
        return AllowlistedResults(
            allowed=allowed, filtered_ids=filtered, reason_by_id=reasons
        )
