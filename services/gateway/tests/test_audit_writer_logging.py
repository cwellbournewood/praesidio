"""Audit-insert failure logging: single ERROR line + DEBUG-only traceback (Task 1.5)."""
from __future__ import annotations

import logging

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from praesidio_gateway.audit.models import Base
from praesidio_gateway.audit.writer import AuditWriter, _short_traceback


def _raise_through_frame() -> None:
    raise RuntimeError("simulated boom")


def test_short_traceback_collapses_to_one_line():
    try:
        _raise_through_frame()
    except RuntimeError as exc:
        msg = _short_traceback(exc)
    # Expect "RuntimeError: simulated boom (<file>:<line> in <fn>)" — single line.
    assert "\n" not in msg
    assert msg.startswith("RuntimeError: simulated boom")
    assert "_raise_through_frame" in msg


@pytest.mark.asyncio
async def test_audit_insert_failure_logs_single_error_line(caplog):
    """A failing insert produces exactly one ERROR-level record at default level.

    Full traceback is only emitted on the DEBUG record (and so is not seen
    when the test captures at ERROR level).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = AuditWriter(engine)

    # A bad row missing required fields — SQLAlchemy will raise during insert.
    bad_row = {"tenant_id": "t"}  # missing decision, chain_hash, etc.

    with caplog.at_level(logging.ERROR, logger="praesidio_gateway.audit.writer"):
        await writer._flush([bad_row])

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    # The ERROR line must be single-line and carry only the short frame.
    rendered = error_records[0].getMessage()
    assert "\n" not in rendered
    assert "audit insert failed" in rendered
    # We never log the raw stacktrace at ERROR.
    assert "Traceback" not in rendered

    await engine.dispose()
