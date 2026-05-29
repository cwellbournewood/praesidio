#!/usr/bin/env bash
# Run a Locust headless soak against the gateway.
#
# Env:
#   SOAK_HOST          gateway base URL (default http://localhost:8080)
#   SOAK_DURATION      Locust -t value         (default 1h)
#   SOAK_RPS           target requests per sec (default 100)
#   SOAK_USERS         peak user count         (default 4 * RPS, capped 800)
#   SOAK_SPAWN_RATE    users/sec to spawn      (default users/30)
#   PRAESIDIO_API_KEY  X-API-Key value         (default praesidio-demo-key)
#
# Output:
#   bench/soak/results/<utc>/{stats,history,failures,exceptions}.csv
#   plus a stdout JSON summary line "LOCUST_SUMMARY {...}".
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SOAK_HOST="${SOAK_HOST:-http://localhost:8080}"
SOAK_DURATION="${SOAK_DURATION:-1h}"
SOAK_RPS="${SOAK_RPS:-100}"

# Heuristic: peak user count = 4 * RPS, capped at 800. Spawn over 30 s.
if [ -z "${SOAK_USERS:-}" ]; then
  SOAK_USERS=$(( SOAK_RPS * 4 ))
  if [ "$SOAK_USERS" -gt 800 ]; then SOAK_USERS=800; fi
fi
SPAWN_RATE="${SOAK_SPAWN_RATE:-$(( SOAK_USERS / 30 + 1 ))}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="$REPO_ROOT/bench/soak/results/$STAMP"
mkdir -p "$OUTDIR"

echo "[soak] host=$SOAK_HOST  duration=$SOAK_DURATION  rps_target=$SOAK_RPS"
echo "[soak] users=$SOAK_USERS  spawn=$SPAWN_RATE/s  out=$OUTDIR"

# `--processes -1` uses all CPUs; remove if you need single-process numbers.
exec locust \
  -f "$REPO_ROOT/bench/soak/locustfile.py" \
  --host "$SOAK_HOST" \
  --headless \
  --users "$SOAK_USERS" \
  --spawn-rate "$SPAWN_RATE" \
  --run-time "$SOAK_DURATION" \
  --csv "$OUTDIR/locust" \
  --csv-full-history \
  --html "$OUTDIR/report.html" \
  --print-stats \
  --only-summary
