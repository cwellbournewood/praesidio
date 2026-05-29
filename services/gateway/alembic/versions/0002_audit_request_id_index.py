"""example migration: add composite index on (tenant_id, request_id)

Revision ID: 0002_audit_request_id_index
Revises: 0001_initial
Create Date: 2026-05-27 00:00:01.000000

This is a near-no-op demonstration migration showing the canonical pattern
for adding an index. It creates a composite ``(tenant_id, request_id)``
index on ``audit_events`` that the admin events lookup-by-request path
benefits from when a tenant has high audit volume. Safe and reversible.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_audit_request_id_index"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_audit_tenant_request",
        "audit_events",
        ["tenant_id", "request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_tenant_request", table_name="audit_events")
