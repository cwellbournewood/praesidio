"""Alembic regression tests.

These exercise the migration scripts against a freshly-created temp SQLite
file. Postgres-specific paths (RLS, GIN, INET) are covered separately by
``tests/test_rls_postgres.py`` under the ``postgres`` marker.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

# Resolve the alembic.ini that ships with the gateway package.
REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _config_for(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    # Force env.py's URL resolution to pick the test DB.
    os.environ["SECTION_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    return cfg


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cur.fetchall()}


def _indexes(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name = ?",
            (table,),
        )
        return {row[0] for row in cur.fetchall() if row[0]}


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "alembic_test.db"


def test_upgrade_head_creates_core_tables(tmp_db: Path) -> None:
    """`alembic upgrade head` against a fresh DB must create the core tables."""
    cfg = _config_for(tmp_db)
    command.upgrade(cfg, "head")

    tables = _tables(tmp_db)
    assert "audit_events" in tables, tables
    assert "lineage_nodes" in tables, tables
    assert "lineage_edges" in tables, tables
    assert "alembic_version" in tables, tables


def test_head_revision_matches_latest_script(tmp_db: Path) -> None:
    """After upgrade, the stamped revision == the script directory head."""
    cfg = _config_for(tmp_db)
    command.upgrade(cfg, "head")

    script_dir = ScriptDirectory.from_config(cfg)
    head_in_scripts = script_dir.get_current_head()

    with sqlite3.connect(tmp_db) as conn:
        cur = conn.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == head_in_scripts


def test_downgrade_then_reupgrade_is_clean(tmp_db: Path) -> None:
    """Stepping down to base and back up to head must leave the schema intact."""
    cfg = _config_for(tmp_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    tables = _tables(tmp_db)
    assert "audit_events" not in tables
    assert "lineage_nodes" not in tables

    command.upgrade(cfg, "head")
    tables = _tables(tmp_db)
    assert "audit_events" in tables
    assert "lineage_nodes" in tables


def test_second_migration_adds_composite_index(tmp_db: Path) -> None:
    """The example second migration adds idx_audit_tenant_request."""
    cfg = _config_for(tmp_db)
    command.upgrade(cfg, "head")
    indexes = _indexes(tmp_db, "audit_events")
    assert "idx_audit_tenant_request" in indexes, indexes


def test_step_by_step_upgrade(tmp_db: Path) -> None:
    """Upgrading one revision at a time must succeed and land at head."""
    cfg = _config_for(tmp_db)
    command.upgrade(cfg, "0001_initial")
    # Only the initial migration has been applied -> no composite index yet.
    indexes_after_first = _indexes(tmp_db, "audit_events")
    assert "idx_audit_tenant_request" not in indexes_after_first

    command.upgrade(cfg, "head")
    indexes_after_head = _indexes(tmp_db, "audit_events")
    assert "idx_audit_tenant_request" in indexes_after_head
