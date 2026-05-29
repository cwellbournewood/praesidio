"""SQLAlchemy 2.x async ORM models for audit + lineage tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# principal_groups is TEXT[] in Postgres (per migration) but tests use SQLite,
# which has no array type. Map to PG ARRAY when on Postgres, JSON elsewhere.
_StringArray = JSON().with_variant(ARRAY(Text()), "postgresql")
# source_ip is INET in Postgres; fall back to String on SQLite.
_IPAddress = String(64).with_variant(INET(), "postgresql")


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    principal_id: Mapped[str | None] = mapped_column(String(256))
    principal_groups: Mapped[Any | None] = mapped_column(_StringArray)
    source_ip: Mapped[str | None] = mapped_column(_IPAddress)
    route: Mapped[str | None] = mapped_column(String(256))
    upstream: Mapped[str | None] = mapped_column(String(256))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(128))
    rule_index: Mapped[int | None] = mapped_column(Integer)
    policy_id: Mapped[str | None] = mapped_column(String(128))
    policy_version: Mapped[str | None] = mapped_column(String(64))
    bundle_digest: Mapped[str | None] = mapped_column(String(64))
    findings: Mapped[Any | None] = mapped_column(JSON)
    transforms: Mapped[Any | None] = mapped_column(JSON)
    request_digest: Mapped[str | None] = mapped_column(String(64))
    response_digest: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    bytes_in: Mapped[int | None] = mapped_column(Integer)
    bytes_out: Mapped[int | None] = mapped_column(Integer)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="enforce", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(16))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (
        Index("idx_audit_tenant_time_orm", "tenant_id", "occurred_at"),
    )


class LineageNode(Base):
    __tablename__ = "lineage_nodes"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ref: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    meta: Mapped[Any | None] = mapped_column(JSON)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"

    parent_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    child_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    relation: Mapped[str] = mapped_column(String(64), primary_key=True)
