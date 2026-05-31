# Benchmarks

Two repeatable harnesses live under `bench/`:

- **Latency** — [`docs/perf-baseline.md`](../perf-baseline.md). Drives the
  gateway end-to-end with stubbed upstream; committed budgets gate release.
- **Detection (precision / recall / F1)** — [`coverage.md`](coverage.md). Runs
  each detector against committed corpora (`bench/eval/corpora/`); a per-label
  recall drop > 5pp vs `bench/eval/baseline.json` fails CI.

```bash
make bench    # latency
make eval     # coverage + regen coverage.md
```
