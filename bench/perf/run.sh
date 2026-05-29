#!/usr/bin/env bash
# Praesidio perf baseline — convenience wrapper.
#
# Default: 500 requests per scenario, concurrency 8, ASGI in-process target.
# Override via env or pass through:
#   REQUESTS=1000 CONCURRENCY=16 bash bench/perf/run.sh
#   bash bench/perf/run.sh --target http --url http://localhost:8080
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REQUESTS="${REQUESTS:-500}"
CONCURRENCY="${CONCURRENCY:-8}"

cd "$REPO_ROOT/services/gateway"

# Prefer `uv run` if present (matches the rest of the dev workflow).
if command -v uv >/dev/null 2>&1; then
  exec uv run python "$REPO_ROOT/bench/perf/latency_baseline.py" \
    --requests "$REQUESTS" --concurrency "$CONCURRENCY" "$@"
fi

exec python "$REPO_ROOT/bench/perf/latency_baseline.py" \
  --requests "$REQUESTS" --concurrency "$CONCURRENCY" "$@"
