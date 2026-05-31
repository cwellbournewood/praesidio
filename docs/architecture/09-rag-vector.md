# 09 · RAG & Vector Database Controls

Status: **architected**, reference adapter (pgvector) shipped, others
stubbed against a common `VectorAdapter` interface.

## Threats

| | |
|---|---|
| **Embedding leakage** | sensitive content embedded into a vector store accessible to people who shouldn't see the source |
| **Cross-tenant retrieval** | tenant A's query returns tenant B's chunks |
| **Stale-PII recall** | content with PII embedded years ago surfaces in a new RAG answer |
| **Memory poisoning** | an attacker writes hostile content into long-term memory; later answers are tainted |
| **Embedding inversion** | embeddings of short strings can be inverted; treating embeddings as "anonymous" is wrong |

## Adapter interface

```python
class VectorAdapter(Protocol):
    async def upsert(self, items: list[VectorItem], principal: Principal) -> None: ...
    async def query(self, q: VectorQuery, principal: Principal) -> list[VectorHit]: ...
    async def delete(self, ids: list[str], principal: Principal) -> None: ...
    async def list(self, *, namespace: str, principal: Principal) -> AsyncIterator[VectorItem]: ...
```

Each `VectorItem` carries:

```python
class VectorItem(BaseModel):
    id: str
    tenant_id: str
    namespace: str
    vector: list[float] | None     # may be None if generated server-side
    payload: dict                  # source text reference, NOT the text
    sensitivity: Sensitivity       # public|internal|confidential|restricted
    acl: ACL                       # readers
    created_at: datetime
    ttl_seconds: int | None
    findings_summary: list[str]    # detector labels found at ingest time
```

## Pre-ingest scan

All inserts pass through the same DLP pipeline as prompts. Detected entities
either:
- block the insert (`fail_mode: closed` for that namespace), or
- tag the item with `sensitivity` + `findings_summary` (used at retrieval
  for ACL filtering), or
- transform the source before embedding (e.g. tokenise PII before
  vectorising — preserves search utility for non-PII, removes PII surface).

## Retrieval mediation

Every query is rewritten to add ACL predicates:

```
SELECT * FROM v WHERE
   tenant_id = :principal.tenant
   AND sensitivity <= :principal.max_sensitivity
   AND acl_readers && :principal.groups
   AND (ttl_expires_at IS NULL OR ttl_expires_at > now())
```

For stores without native predicate pushdown (FAISS, Chroma in some modes),
the gateway maintains a sidecar index of allowed IDs.

## Memory governance

Long-term agent memory uses the same vector adapter with:
- mandatory TTL (default 7 days),
- semantic expiry: an embedding whose nearest neighbour to a "stale topic"
  vector falls below threshold gets pruned,
- write filter: memory writes pass through DLP — anything sensitive is
  refused (memory should be sparse and intentional, not a dump).

## Supported stores

| Store | Status | Notes |
|---|---|---|
| pgvector | ✅ reference | full predicate pushdown |
| Pinecone | 🟦 stub | metadata-filter based ACL |
| Weaviate | 🟦 stub | tenants + auth header |
| Milvus | 🟦 stub | partitions for tenancy |
| OpenSearch (vector) | 🟦 stub | RBAC integration |
| Chroma | 🟦 stub | collection-per-tenant |
| FAISS | 🟦 stub | sidecar ACL index |

## Lineage

Every retrieval produces lineage edges (see
[`06-audit-lineage.md`](06-audit-lineage.md#lineage-reconstruction)) — the
generated output is linked back to the specific chunks it was conditioned
on, and from there to the ingest events that put them in the store.
