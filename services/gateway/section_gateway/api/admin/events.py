"""GET /admin/events — filterable audit log reader."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ...audit.models import AuditEvent
from ...auth import PrincipalDep
from ...state import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/events")
async def list_events(
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
    tenant: str | None = Query(None),
    decision: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    cursor: str | None = Query(None),
    paged: bool = Query(False, description="If true, return {items, next_cursor}; otherwise a bare JSON array."),
):
    """List audit events for the caller's tenant.

    By default returns a **bare JSON array** of event rows — kept stable for
    shell tooling (`jq`, `curl | jq '.[0]'`, etc.). Pass ``?paged=true`` to
    get the paginated envelope ``{items, next_cursor}``.
    """
    sm = async_sessionmaker(state.engine, expire_on_commit=False)
    async with sm() as s:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
        # Tenant scoping: caller's tenant unless they passed an explicit one.
        stmt = stmt.where(AuditEvent.tenant_id == (tenant or principal.tenant_id))
        if decision:
            stmt = stmt.where(AuditEvent.decision == decision)
        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)
        if until:
            stmt = stmt.where(AuditEvent.occurred_at <= until)
        if cursor:
            stmt = stmt.where(AuditEvent.id < cursor)
        res = await s.execute(stmt)
        rows = res.scalars().all()

    def _to_dict(r: AuditEvent) -> dict[str, Any]:
        return {c.name: getattr(r, c.name) for c in r.__table__.columns}

    items = [_to_dict(r) for r in rows]
    if paged:
        return {
            "items": items,
            "next_cursor": rows[-1].id if rows else None,
        }
    return items
