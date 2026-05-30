"""Alembic environment for Section gateway.

This script supports two operating modes:

* **Offline** — emits SQL to stdout without connecting to a database. Useful
  for review and for shipping a SQL bundle to a DBA.
* **Online** — opens a (sync) connection and applies migrations. Even though
  the gateway uses ``asyncpg``/``aiosqlite`` at runtime, Alembic itself runs
  with the sync ``psycopg``/``sqlite3`` drivers — we strip ``+asyncpg`` /
  ``+aiosqlite`` from the URL automatically.

DSN resolution order:

1. ``-x url=...`` on the command line (highest priority).
2. ``SECTION_DATABASE_URL`` environment variable.
3. ``DATABASE_URL`` environment variable.
4. The placeholder ``sqlalchemy.url`` from ``alembic.ini`` (lowest).
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the gateway package importable so migrations can reference ORM metadata
# when convenient (e.g. ``--autogenerate``).
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from section_gateway.audit.models import Base  # noqa: E402

    target_metadata = Base.metadata
except Exception:  # pragma: no cover — autogenerate is optional
    target_metadata = None


config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: fileConfig's default (True) silences
    # every logger already constructed at import time — that breaks pytest's
    # caplog when the gateway is imported before alembic runs in the test
    # suite. Production migrations never run in the same process as the
    # gateway, so this is purely defensive.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _resolve_url() -> str:
    """Pick the database URL, normalising to a sync driver Alembic can use."""
    cmd_kwargs = context.get_x_argument(as_dictionary=True)
    raw = (
        cmd_kwargs.get("url")
        or os.environ.get("SECTION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )
    if not raw:
        raise RuntimeError(
            "No database URL configured. Set SECTION_DATABASE_URL or pass "
            "-x url=... to `alembic`."
        )
    # SQLAlchemy async drivers must be swapped for their sync counterparts.
    replacements = {
        "postgresql+asyncpg://": "postgresql+psycopg://",
        "postgresql+psycopg2://": "postgresql+psycopg://",
        "sqlite+aiosqlite://": "sqlite://",
    }
    for src, dst in replacements.items():
        if raw.startswith(src):
            raw = dst + raw[len(src):]
            break
    return raw


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite cannot ALTER most column attributes; use batch mode so
            # downgrades / future schema edits work in tests.
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
