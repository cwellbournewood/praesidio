# Praesidio benchmarks

Three independent benchmark suites under one roof:

| Dir | What | Entrypoint |
|---|---|---|
| `perf/` | End-to-end latency baseline (in-process ASGI, no network) | `bench/perf/run.sh` |
| `soak/` | Locust load + soak test against a running gateway | `bench/soak/run-soak.sh` |
| `eval/` | DLP coverage + precision/recall evaluation | `bench/eval/run_eval.py` |

## Quick start

```bash
# Latency baseline (5 minutes, no network):
make bench-perf

# 1-hour soak at 100 RPS against a running gateway:
make bench-soak                                   # uses defaults
SOAK_DURATION=15m SOAK_RPS=50 make bench-soak     # shorter / lighter

# DLP detector evaluation (uses committed corpora):
make eval
```

## Extra dependencies

The bench tools intentionally live outside the gateway's `pyproject.toml`
so they don't bloat production builds. Install with:

```bash
# From the repo root
uv pip install -r bench/requirements.txt
# or with stdlib pip:
python -m pip install -r bench/requirements.txt
```

## Results layout

Every run writes a timestamped artefact directory; nothing is overwritten.

```
bench/
├── perf/results/<utc>.json                   # 1 file per perf run
├── soak/results/<utc>/                       # locust CSVs + HTML + REPORT.md
└── eval/results/<utc>.json                   # 1 file per eval run
```

The eval suite also writes a single committed `bench/eval/baseline.json`
which the regression-check script compares against on each run.
