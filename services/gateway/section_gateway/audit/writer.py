"""Batched async audit writer.

A bounded asyncio queue feeds a background coroutine that flushes either
when ``batch_size`` is hit or every ``flush_interval`` seconds. The chain
hash is computed atomically with the insert per tenant.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..obs.metrics import AUDIT_WRITE_TOTAL
from .chain import compute_chain_hash
from .models import AuditEvent, LineageEdge, LineageNode
from .sinks.splunk_hec import SplunkHECSink
from .sinks.webhook import SiemWebhookSink

_log = logging.getLogger(__name__)


def _short_traceback(exc: BaseException) -> str:
    """Return a single-line summary: ``Type: message (file:line in fn)``.

    Uses the innermost frame (where the exception was raised) and collapses
    any newlines in the exception message so the ERROR log stays one line.
    """
    msg = " | ".join(line.strip() for line in str(exc).splitlines() if line.strip())
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return f"{type(exc).__name__}: {msg}"
    frame = tb[-1]
    return (
        f"{type(exc).__name__}: {msg} "
        f"({frame.filename}:{frame.lineno} in {frame.name})"
    )


class AuditWriter:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        queue_max: int = 10_000,
        splunk: SplunkHECSink | None = None,
        webhook: SiemWebhookSink | None = None,
    ) -> None:
        self._engine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )
        self._batch = batch_size
        self._interval = flush_interval
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_max)
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._splunk = splunk
        self._webhook = webhook
        self._chain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="audit-writer")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
        if self._splunk:
            await self._splunk.close()
        if self._webhook:
            await self._webhook.close()

    # -- public API -------------------------------------------------------

    async def submit(self, row: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(row)
        except asyncio.QueueFull:
            _log.error("audit queue full; dropping event tenant=%s", row.get("tenant_id"))
            AUDIT_WRITE_TOTAL.labels(outcome="dropped").inc()

    async def write_one(self, row: dict[str, Any]) -> str:
        """Bypass the queue (used by tests / urgent paths). Returns chain_hash."""
        return await self._insert_with_chain(row)

    async def flush(self) -> None:
        """Drain anything currently queued and insert it synchronously.

        Used by tests and by graceful-shutdown paths that need a hard
        guarantee the rows have hit the DB before continuing. Safe to
        call concurrently with the background writer — the queue is
        thread-safe and we never block the background task longer than
        one row.
        """
        buf: list[dict[str, Any]] = []
        while True:
            try:
                buf.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if buf:
            await self._flush(buf)

    async def append_lineage(
        self,
        *,
        tenant_id: str,
        request_id: str,
        nodes: list[tuple[str, str, dict[str, Any] | None]],
        edges: list[tuple[str, str, str]],
    ) -> None:
        async with self._session() as s:
            for nid, kind, meta in nodes:
                s.add(LineageNode(id=nid, tenant_id=tenant_id, request_id=request_id, kind=kind, ref=request_id, meta=meta))
            for parent, child, rel in edges:
                s.add(LineageEdge(parent_id=parent, child_id=child, relation=rel))
            await s.commit()

    # -- internals --------------------------------------------------------

    @asynccontextmanager
    async def _session(self):
        async with self._sessionmaker() as s:
            yield s

    async def _run(self) -> None:
        buf: list[dict[str, Any]] = []
        while not self._stop.is_set():
            timeout = self._interval
            try:
                row = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                buf.append(row)
            except TimeoutError:
                pass
            # Drain anything else without blocking.
            while len(buf) < self._batch:
                try:
                    buf.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if buf:
                await self._flush(buf)
                buf = []
        # Final drain.
        while not self._queue.empty():
            try:
                buf.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if buf:
            await self._flush(buf)

    async def _flush(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            try:
                await self._insert_with_chain(row)
                AUDIT_WRITE_TOTAL.labels(outcome="ok").inc()
            except Exception as exc:
                AUDIT_WRITE_TOTAL.labels(outcome="err").inc()
                # Default-level: single-line ERROR with first frame only.
                _log.error("audit insert failed: %s", _short_traceback(exc))
                # Full stacktrace only at DEBUG.
                _log.debug("audit insert traceback", exc_info=exc)
        if self._splunk and self._splunk.enabled:
            await self._splunk.emit(rows)
        if self._webhook and self._webhook.enabled:
            # Webhook is best-effort and never raises into the writer loop.
            await self._webhook.emit(rows)

    async def _last_chain_hash(self, session: AsyncSession, tenant_id: str) -> str | None:
        stmt = (
            select(AuditEvent.chain_hash)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(desc(AuditEvent.occurred_at), desc(AuditEvent.id))
            .limit(1)
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def _insert_with_chain(self, row: dict[str, Any]) -> str:
        tenant_id = row["tenant_id"]
        async with self._chain_locks[tenant_id], self._session() as s:
            prev = await self._last_chain_hash(s, tenant_id)
            row = {**row}
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("occurred_at", datetime.now(UTC))
            row["prev_hash"] = prev
            row["chain_hash"] = compute_chain_hash(prev, row)
            ev = AuditEvent(**row)
            s.add(ev)
            await s.commit()
            return row["chain_hash"]
