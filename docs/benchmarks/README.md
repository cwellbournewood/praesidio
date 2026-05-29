# Benchmarks

A repeatable benchmark harness lives at `services/gateway/bench/`. Numbers
below are placeholders until we publish official runs from CI; each release
will refresh them via the `bench` job and update this page.

## Latency

| Operation | p50 | p95 | p99 | hardware |
|---|---:|---:|---:|---|
| Regex + secrets only | tbd | tbd | tbd | tbd |
| + Presidio | tbd | tbd | tbd | tbd |
| + semantic classifier | tbd | tbd | tbd | tbd |
| Full pipeline + tokenise + audit | tbd | tbd | tbd | tbd |
| End-to-end (with mocked upstream) | tbd | tbd | tbd | tbd |

## Throughput

Target: ≥ 5k req/s per replica for short prompts (≤ 1KB), linear scale.

## False-positive validation

Curated corpus + ground truth in `bench/fp-corpus/`. Target FP rate < 2%
on validated policies.

## Anonymisation utility

We measure answer quality on a held-out QA dataset with and without
anonymisation. Target: < 5% answer-quality regression on standard QA.
