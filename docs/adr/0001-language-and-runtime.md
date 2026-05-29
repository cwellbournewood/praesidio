# ADR-0001 · Language and runtime for the gateway

Date: 2026-05-27 · Status: Accepted

## Context

The gateway is on the hot path for every LLM call in the enterprise. It must:
host a high-quality NLP / DLP pipeline (Presidio, spaCy, ONNX classifiers);
proxy streaming responses with minimal added latency; integrate fast; be
operable by enterprise SRE teams.

Candidates considered:
1. Python (FastAPI + uvicorn + httpx)
2. Go gateway + Python ML sidecar (gRPC)
3. Rust (axum / hyper) + Python ML sidecar
4. Pure Node/TypeScript (Hono / fastify)

## Decision

**Python (FastAPI + uvicorn + httpx)** for the gateway as a whole, single
process. The pyproject is set up so a future split into "edge proxy in
Rust/Go + DLP sidecar in Python" is a refactor, not a rewrite, by keeping the
DLP pipeline behind a clean `Detector` / `Pipeline` interface and the
upstream proxy behind a `ProviderAdapter` interface.

## Consequences

- ➕ Best-in-class NLP/ML ecosystem (Presidio, spaCy, transformers, ONNX).
- ➕ Single deploy artefact for MVP — faster to credible.
- ➕ Async IO is good enough for the streaming pass-through pattern.
- ➖ Raw proxy throughput is below Go/Rust. We document the split path; we
  ship benchmarks; we accept this for the open-source MVP.
- ➖ Python deployment in regulated environments needs care (uv, pinned
  wheels, vulnerability scanning) — addressed via the supplied Dockerfile.

## Revisit when

- p99 throughput per replica drops below the documented target,
- or a paying customer requires sub-5ms p99 at edge.
