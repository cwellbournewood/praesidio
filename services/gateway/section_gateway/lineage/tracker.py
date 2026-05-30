"""Per-request lineage DAG builder.

The tracker is created at the start of each request and appended to as the
gateway makes derivation decisions (prompt → retrieval → tool → output).
At the end of the request its nodes/edges are flushed through the audit
writer.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class _Node:
    id: str
    kind: str
    meta: dict[str, Any] | None = None


@dataclass(slots=True)
class _Edge:
    parent_id: str
    child_id: str
    relation: str


@dataclass
class LineageTracker:
    request_id: str
    tenant_id: str
    nodes: list[_Node] = field(default_factory=list)
    edges: list[_Edge] = field(default_factory=list)

    def add(self, kind: str, meta: dict[str, Any] | None = None) -> str:
        nid = str(uuid.uuid4())
        self.nodes.append(_Node(id=nid, kind=kind, meta=meta))
        return nid

    def link(self, parent_id: str, child_id: str, relation: str = "derived_from") -> None:
        self.edges.append(_Edge(parent_id=parent_id, child_id=child_id, relation=relation))

    async def flush(self, writer) -> None:
        await writer.append_lineage(
            tenant_id=self.tenant_id,
            request_id=self.request_id,
            nodes=[(n.id, n.kind, n.meta) for n in self.nodes],
            edges=[(e.parent_id, e.child_id, e.relation) for e in self.edges],
        )
