"""GET /admin/lineage — request DAGs.

Two endpoints:

* ``GET /admin/lineage/{request_id}`` returns the DAG for a single request
  in the shape the UI expects::

      {
        "request_id": "...",
        "nodes": [{"id", "kind", "label", "ref", "meta", "audit_event_id"}, ...],
        "edges": [{"parent_id", "child_id", "relation"}, ...]
      }

  ``label`` is a human-readable derivative of ``ref`` so callers don't need
  to inspect ``meta`` to render a node title; the original ``ref`` is also
  preserved for operators who want the full opaque reference.

* ``GET /admin/lineage`` returns the N most recent ``request_id``s for the
  caller's tenant so the bare ``/lineage`` URL has somewhere to land
  instead of 404-ing. Each entry includes the timestamp of the first
  recorded node so the UI can render an "X ago" hint.

Both endpoints are tenant-scoped via ``principal.tenant_id``; the RLS
policies on ``lineage_nodes`` / ``lineage_edges`` provide defence-in-depth
when Postgres is configured (see ``migrations/0001_init.sql``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ...audit.models import AuditEvent, LineageEdge, LineageNode
from ...auth import PrincipalDep
from ...state import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])


def _label_for(node: LineageNode) -> str:
    """Derive a short display label from the opaque ``ref`` and ``meta``.

    Rules of thumb:
      - If meta has a "label" or "name" key, prefer it.
      - Otherwise take the last path segment of ``ref`` so URIs render
        compactly (e.g. ``ollama://llama-3.1-70b`` → ``llama-3.1-70b``).
    """
    meta = node.meta or {}
    for k in ("label", "name", "title"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    ref = node.ref or node.kind
    # Strip URI-ish prefixes for readability.
    for sep in ("://", ":", "/"):
        if sep in ref:
            ref = ref.rsplit(sep, 1)[-1] or ref
    return ref or node.kind


@router.get("/lineage")
async def list_recent_lineage(
    principal: PrincipalDep,
    limit: int = Query(20, ge=1, le=200),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Return the N most recent request_ids that have lineage rows.

    Powers the bare ``/lineage`` index page in the UI. Falls back to the
    audit table if no lineage rows exist yet — the UI can still link
    through to a request even before its DAG is populated, and the
    detail endpoint will return an empty graph in that case.
    """
    sm = async_sessionmaker(state.engine, expire_on_commit=False)
    async with sm() as s:
        # Subquery: first-seen timestamp per request_id with a lineage node.
        q = (
            select(
                LineageNode.request_id.label("request_id"),
                func.min(LineageNode.occurred_at).label("started_at"),
                func.count(LineageNode.id).label("node_count"),
            )
            .where(LineageNode.tenant_id == principal.tenant_id)
            .group_by(LineageNode.request_id)
            .order_by(desc("started_at"))
            .limit(limit)
        )
        rows = (await s.execute(q)).all()

        items: list[dict[str, Any]] = [
            {
                "request_id": r.request_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "node_count": int(r.node_count or 0),
                "source": "lineage",
            }
            for r in rows
        ]

        # Backfill from recent audit events if lineage table is empty.
        if not items:
            aq = (
                select(
                    AuditEvent.request_id,
                    func.min(AuditEvent.occurred_at).label("started_at"),
                )
                .where(AuditEvent.tenant_id == principal.tenant_id)
                .group_by(AuditEvent.request_id)
                .order_by(desc("started_at"))
                .limit(limit)
            )
            arows = (await s.execute(aq)).all()
            items = [
                {
                    "request_id": r.request_id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "node_count": 0,
                    "source": "audit",
                }
                for r in arows
            ]

    return {"items": items, "tenant_id": principal.tenant_id}


@router.get("/lineage/{request_id}")
async def get_lineage(
    principal: PrincipalDep,
    request_id: str = Path(..., min_length=1),
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Return the DAG for a single request.

    Empty ``nodes``/``edges`` means the request has no recorded lineage
    yet (or the caller's tenant does not own this request) — the UI
    treats this as the empty state rather than a 404 so operators can
    paste a request_id and see whether anything is recorded.
    """
    sm = async_sessionmaker(state.engine, expire_on_commit=False)
    async with sm() as s:
        nodes_q = await s.execute(
            select(LineageNode).where(
                LineageNode.request_id == request_id,
                LineageNode.tenant_id == principal.tenant_id,
            )
        )
        nodes = list(nodes_q.scalars().all())
        node_ids = [n.id for n in nodes]
        edges: list[LineageEdge] = []
        if node_ids:
            edges_q = await s.execute(
                select(LineageEdge).where(
                    LineageEdge.parent_id.in_(node_ids)
                    | LineageEdge.child_id.in_(node_ids)
                )
            )
            edges = list(edges_q.scalars().all())

        # Best-effort: associate the request_id with one audit event so the
        # UI can deep-link "open in events" from any node.
        ae = (
            await s.execute(
                select(AuditEvent.id)
                .where(
                    AuditEvent.request_id == request_id,
                    AuditEvent.tenant_id == principal.tenant_id,
                )
                .order_by(desc(AuditEvent.occurred_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    return {
        "request_id": request_id,
        "tenant_id": principal.tenant_id,
        "audit_event_id": ae,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "label": _label_for(n),
                "ref": n.ref,
                "meta": n.meta,
                "audit_event_id": ae,
            }
            for n in nodes
        ],
        "edges": [
            {"parent_id": e.parent_id, "child_id": e.child_id, "relation": e.relation}
            for e in edges
        ],
    }
