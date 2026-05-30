"""Vector-store API: DLP-on-write and ACL-on-read.

Exposes:

* ``POST /v1/vectors/{store}/upsert`` — accepts ``{documents:[{id,text,metadata}]}``,
  runs ``scan_on_write`` to substitute placeholders for sensitive
  entities (and persist the reversal map in the vault), then writes the
  sanitised text + embedding to the underlying store.

* ``POST /v1/vectors/{store}/query`` — runs the vector search, then
  filters the result set against ``documents_acl`` so the caller never
  sees a document they don't own or have been granted access to.

The connector instances themselves are not constructed by this router —
operators wire them in via :func:`register_connector` from
``main.py`` (see the marked vectors block). This keeps the router pure
and testable while letting deployment overlays (Helm, Compose) decide
which stores to enable.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from ..auth import PrincipalDep
from ..vectors import VectorConnector, VectorDocument

router = APIRouter(prefix="/v1/vectors", tags=["vectors"])


# ---- registry --------------------------------------------------------------

_CONNECTORS: dict[str, VectorConnector] = {}


def register_connector(name: str, connector: VectorConnector) -> None:
    """Register a connector under ``name`` (the path segment in ``/v1/vectors/{store}``).

    Idempotent — re-registering the same name replaces the previous
    connector, which is what an operator wants when hot-reloading config.
    """
    _CONNECTORS[name] = connector


def unregister_connector(name: str) -> None:
    _CONNECTORS.pop(name, None)


def list_connectors() -> dict[str, VectorConnector]:
    return dict(_CONNECTORS)


def _get(name: str) -> VectorConnector:
    c = _CONNECTORS.get(name)
    if c is None:
        raise HTTPException(
            status_code=404,
            detail=f"vector store '{name}' is not configured",
        )
    return c


# ---- request / response models ---------------------------------------------


class _DocIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=256)
    text: str = Field(..., min_length=1, max_length=200_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpsertRequest(BaseModel):
    documents: list[_DocIn] = Field(..., min_length=1, max_length=512)
    request_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional client-supplied request id; if omitted, a synthetic one is used.",
    )


class UpsertResponse(BaseModel):
    store: str
    upserted: list[str]
    blocked: list[str]
    placeholders_by_doc: dict[str, list[str]]
    findings_by_doc: dict[str, list[dict[str, Any]]]


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    top_k: int = Field(default=10, ge=1, le=200)


class QueryHit(BaseModel):
    id: str
    score: float
    text: str | None
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    store: str
    hits: list[QueryHit]
    filtered_ids: list[str]
    reasons: dict[str, str]


class StoreInfo(BaseModel):
    name: str
    connector: str


class StoresResponse(BaseModel):
    stores: list[StoreInfo]


# ---- routes ----------------------------------------------------------------


@router.get("", response_model=StoresResponse)
async def list_stores(
    _principal: PrincipalDep,
) -> StoresResponse:
    """List configured vector stores."""
    return StoresResponse(
        stores=[
            StoreInfo(name=name, connector=c.name)
            for name, c in sorted(_CONNECTORS.items())
        ]
    )


@router.post("/{store}/upsert", response_model=UpsertResponse)
async def upsert(
    payload: UpsertRequest,
    principal: PrincipalDep,
    store: str = Path(..., min_length=1, max_length=64),
) -> UpsertResponse:
    """Run DLP-on-write and persist documents into ``store``."""
    connector = _get(store)
    request_id = payload.request_id or f"vec:{store}:{principal.tenant_id}"
    docs = [VectorDocument(id=d.id, text=d.text, metadata=d.metadata) for d in payload.documents]
    result = await connector.scan_on_write(
        docs,
        tenant_id=principal.tenant_id,
        request_id=request_id,
    )
    return UpsertResponse(
        store=store,
        upserted=[d.id for d in result.documents],
        blocked=result.blocked_doc_ids,
        placeholders_by_doc=result.placeholders_by_doc,
        findings_by_doc={
            doc_id: [
                {
                    "label": f.label,
                    "start": f.start,
                    "end": f.end,
                    "confidence": f.confidence,
                }
                for f in findings
            ]
            for doc_id, findings in result.findings_by_doc.items()
        },
    )


@router.post("/{store}/query", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    principal: PrincipalDep,
    store: str = Path(..., min_length=1, max_length=64),
) -> QueryResponse:
    """Query ``store`` and return only ACL-visible documents."""
    connector = _get(store)
    res = await connector.validate_retrieval(
        payload.query,
        tenant_id=principal.tenant_id,
        principal_id=principal.user_id,
        principal_groups=list(principal.groups),
        top_k=payload.top_k,
    )
    return QueryResponse(
        store=store,
        hits=[
            QueryHit(id=a.id, score=a.score, text=a.text, metadata=a.metadata)
            for a in res.allowed
        ],
        filtered_ids=res.filtered_ids,
        reasons=res.reason_by_id,
    )
