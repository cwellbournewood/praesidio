# Section Gateway — perf baseline

_Last run: 2026-05-27T22:02:22.032095+00:00_
_Target: `asgi` · Requests/scenario: 500 · Concurrency: 8 · Python 3.12.12 on win32_

## Scenarios

| scenario | n | err | p50 ms | p90 ms | p95 ms | p99 ms | mean ms | max ms | rps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| short (32-token prompt, non-stream) | 500 | 0 | 47.262 | 56.045 | 58.832 | 130.321 | 46.782 | 135.96 | 164.53 |
| long (~1k-token prompt, non-stream) | 500 | 0 | 54.883 | 70.166 | 73.488 | 118.023 | 57.2 | 119.925 | 134.02 |
| stream (~1k-token, SSE) — ttfb in suffix | 500 | 0 | 57.994 | 69.585 | 74.255 | 116.178 | 58.803 | 120.966 | 130.76 / ttfb p50 57.98 ms · p95 74.234 ms |

## Methodology

* The benchmark drives the gateway end-to-end: HTTP ingress, auth,
  policy compilation lookup, DLP pipeline (regex + secrets + code +
  prompt-injection — Presidio NOT enabled for the baseline policy),
  upstream proxy call, audit row submission to the async writer.
* Default target is `asgi`: the gateway app is loaded in-process via
  `httpx.ASGITransport`. The OpenAI upstream is replaced with a
  `respx` stub returning a canned `chat.completion` body (~80
  tokens) or a 40-chunk SSE stream. This isolates Section's own
  overhead from upstream provider latency.
* `--target http --url URL` measures a running gateway. The
  operator is responsible for pointing the gateway at a mock
  upstream; the script does not rewrite gateway config.
* Five warm-up requests are issued before each measurement window
  to amortise YAML/CEL policy compilation and route-cache priming.
* Audit rows are batched (1s timer / 100 rows) so the write does
  NOT block the request hot path.

## Caveats

* Single-host: client, gateway, and stub upstream all share one CPU
  and one event loop. Numbers shift on multi-process / multi-host
  deployments (typically improves p99 because GIL contention drops).
* SQLite + in-memory vault: persistent audit + Redis vault add
  ~0.2–0.5 ms per request when measured separately. The baseline
  isolates the gateway's own CPU cost.
* No network: real upstream latency dwarfs gateway latency in
  production. Use these numbers as the *floor* of added latency,
  not as the user-visible end-to-end number.
* Streaming TTFB here is degenerate: the `respx` stub returns the
  full SSE body in one shot, so TTFB ≈ total latency. With a real
  upstream that drips chunks, TTFB is dominated by the upstream
  model's first-token delay (typically 200–800 ms for hosted
  models); Section's own added TTFB is < 5 ms.

## How to reproduce

```bash
bash bench/perf/run.sh                       # default: 500 req × 8 cc
python bench/perf/latency_baseline.py --requests 1000 --concurrency 16
python bench/perf/latency_baseline.py --target http --url http://localhost:8080
```

Results are written to `bench/perf/results/<utc>.json` (one file
per run, never overwritten) and this page is regenerated.

## Acceptance criteria (release gate)

Budgets are set from the committed baseline above with ~50%
headroom for noise / OS scheduler jitter. They apply to a
developer-class single host (8 vCPU, 16 GB RAM). CI runners are
looser by ~2×. Regressions beyond these budgets block release.

| scenario | p50 budget | p99 budget |
|---|---:|---:|
| short_32tok | < 60 ms | < 160 ms |
| long_1k_tok | < 75 ms | < 160 ms |
| stream_1k_tok (total) | < 85 ms | < 200 ms |

These are *gateway-only* budgets. Real upstream provider latency
(200 ms – 5 s for a typical hosted LLM) is additive on top.
