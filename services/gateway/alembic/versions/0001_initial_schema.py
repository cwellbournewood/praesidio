"""initial schema: audit_events, lineage_nodes, lineage_edges + RLS

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27 00:00:00.000000

Ports the canonical initial schema from
``services/gateway/migrations/0001_init.sql``. The SQL file remains in the
tree for the Postgres container's ``docker-entrypoint-initdb.d`` (a different
code path that only fires on a fresh data volume) — Alembic owns ongoing
schema evolution everywhere else.

The migration is dialect-aware: Postgres gets the full feature set
(``UUID`` / ``TIMESTAMPTZ`` / ``TEXT[]`` / ``INET`` / ``JSONB`` / GIN indexes
/ Row-Level Security policies). SQLite gets a faithful, type-compatible
subset suitable for unit tests.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID

from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    pg = _is_postgres()

    if pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ---------------- audit_events ----------------
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=False) if pg else sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.Text() if pg else sa.String(128), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()" if pg else "CURRENT_TIMESTAMP"),
        ),
        sa.Column("request_id", sa.Text() if pg else sa.String(64), nullable=False),
        sa.Column("principal_id", sa.Text() if pg else sa.String(256)),
        sa.Column("principal_groups", ARRAY(sa.Text()) if pg else sa.JSON()),
        sa.Column("source_ip", INET() if pg else sa.String(64)),
        sa.Column("route", sa.Text() if pg else sa.String(256)),
        sa.Column("upstream", sa.Text() if pg else sa.String(256)),
        sa.Column("decision", sa.Text() if pg else sa.String(32), nullable=False),
        sa.Column("rule_id", sa.Text() if pg else sa.String(128)),
        sa.Column("rule_index", sa.Integer()),
        sa.Column("policy_id", sa.Text() if pg else sa.String(128)),
        sa.Column("policy_version", sa.Text() if pg else sa.String(64)),
        sa.Column("bundle_digest", sa.Text() if pg else sa.String(64)),
        sa.Column("findings", JSONB() if pg else sa.JSON()),
        sa.Column("transforms", JSONB() if pg else sa.JSON()),
        sa.Column("request_digest", sa.Text() if pg else sa.String(64)),
        sa.Column("response_digest", sa.Text() if pg else sa.String(64)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("bytes_in", sa.Integer()),
        sa.Column("bytes_out", sa.Integer()),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "mode", sa.Text() if pg else sa.String(16),
            nullable=False, server_default="enforce",
        ),
        sa.Column("reason", sa.Text()),
        sa.Column("severity", sa.Text() if pg else sa.String(16)),
        sa.Column("prev_hash", sa.Text() if pg else sa.String(64)),
        sa.Column("chain_hash", sa.Text() if pg else sa.String(64), nullable=False),
        sa.Column("signature", sa.Text() if pg else sa.String(256)),
    )

    op.create_index(
        "idx_audit_tenant_time", "audit_events",
        ["tenant_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "idx_audit_tenant_principal_time", "audit_events",
        ["tenant_id", "principal_id", sa.text("occurred_at DESC")],
    )
    op.create_index("idx_audit_request_id", "audit_events", ["request_id"])
    op.create_index(
        "idx_audit_decision", "audit_events",
        ["tenant_id", "decision", sa.text("occurred_at DESC")],
    )
    if pg:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_findings_gin "
            "ON audit_events USING GIN (findings jsonb_path_ops)"
        )

    # ---------------- lineage_nodes ----------------
    op.create_table(
        "lineage_nodes",
        sa.Column("id", UUID(as_uuid=False) if pg else sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.Text() if pg else sa.String(128), nullable=False),
        sa.Column("request_id", sa.Text() if pg else sa.String(64), nullable=False),
        sa.Column("kind", sa.Text() if pg else sa.String(32), nullable=False),
        sa.Column("ref", sa.Text() if pg else sa.String(256), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()" if pg else "CURRENT_TIMESTAMP"),
        ),
        sa.Column("meta", JSONB() if pg else sa.JSON()),
    )
    op.create_index(
        "idx_lineage_nodes_request", "lineage_nodes", ["tenant_id", "request_id"]
    )
    op.create_index(
        "idx_lineage_nodes_kind", "lineage_nodes", ["tenant_id", "kind"]
    )

    # ---------------- lineage_edges ----------------
    op.create_table(
        "lineage_edges",
        sa.Column(
            "parent_id",
            UUID(as_uuid=False) if pg else sa.String(36),
            sa.ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "child_id",
            UUID(as_uuid=False) if pg else sa.String(36),
            sa.ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "relation", sa.Text() if pg else sa.String(64), primary_key=True
        ),
    )
    op.create_index("idx_lineage_edges_child", "lineage_edges", ["child_id"])

    # ---------------- RLS (Postgres only) ----------------
    # FORCE is critical: the table owner (the role that ran this migration)
    # bypasses ENABLE-only RLS, which silently breaks multi-tenant isolation
    # when the application connects with that same role. FORCE applies the
    # policy regardless of role, including the owner. Operators with the
    # wildcard `section.tenant_id = '*'` setting can still see everything.
    if pg:
        for table in ("audit_events", "lineage_nodes"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
            )
            op.execute(
                f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (
                    tenant_id = current_setting('section.tenant_id', true)
                    OR current_setting('section.tenant_id', true) = '*'
                )
                WITH CHECK (
                    tenant_id = current_setting('section.tenant_id', true)
                    OR current_setting('section.tenant_id', true) = '*'
                )
                """
            )


def downgrade() -> None:
    pg = _is_postgres()

    if pg:
        for table in ("audit_events", "lineage_nodes"):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_index("idx_lineage_edges_child", table_name="lineage_edges")
    op.drop_table("lineage_edges")
    op.drop_index("idx_lineage_nodes_kind", table_name="lineage_nodes")
    op.drop_index("idx_lineage_nodes_request", table_name="lineage_nodes")
    op.drop_table("lineage_nodes")
    if pg:
        op.execute("DROP INDEX IF EXISTS idx_audit_findings_gin")
    op.drop_index("idx_audit_decision", table_name="audit_events")
    op.drop_index("idx_audit_request_id", table_name="audit_events")
    op.drop_index("idx_audit_tenant_principal_time", table_name="audit_events")
    op.drop_index("idx_audit_tenant_time", table_name="audit_events")
    op.drop_table("audit_events")
