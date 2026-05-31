"""Compare the latest eval run vs the committed baseline.

Fails (exit 1) when any per-label *recall* dropped more than
``--recall-tolerance`` (default 0.05 = 5 percentage points). Precision and
F1 regressions are surfaced but do not gate.

Usage:

    python bench/eval/regression-check.py
    python bench/eval/regression-check.py --recall-tolerance 0.03
    python bench/eval/regression-check.py --results bench/eval/results/<x>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "bench" / "eval" / "baseline.json"
RESULTS_DIR = REPO_ROOT / "bench" / "eval" / "results"


def _latest_results() -> Path:
    files = sorted(RESULTS_DIR.glob("*.json"))
    if not files:
        raise SystemExit("no eval results found — run bench/eval/run_eval.py first")
    return files[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=None,
                        help="results json (default: latest in bench/eval/results/)")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--recall-tolerance", type=float, default=0.05,
                        help="max allowed drop in per-label recall (default 0.05)")
    args = parser.parse_args()

    results_path = args.results or _latest_results()
    if not args.baseline.exists():
        raise SystemExit(f"baseline missing: {args.baseline}")

    results = json.loads(results_path.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    failures: list[str] = []
    warnings: list[str] = []

    for c in results["corpora"]:
        name = c["corpus"]
        base_c = baseline["corpora"].get(name)
        if not base_c:
            warnings.append(f"[{name}] no baseline yet — skipping")
            continue
        for lab, m in c["per_label"].items():
            base_m = base_c["per_label"].get(lab)
            if not base_m:
                warnings.append(f"[{name}] {lab}: new label, no baseline")
                continue
            d_recall = m["recall"] - base_m["recall"]
            d_prec = m["precision"] - base_m["precision"]
            d_f1 = m["f1"] - base_m["f1"]
            if d_recall < -args.recall_tolerance:
                failures.append(
                    f"[{name}] {lab}: recall regressed {base_m['recall']:.3f} "
                    f"-> {m['recall']:.3f} (Δ={d_recall:+.3f})"
                )
            elif d_recall < -0.01:
                warnings.append(
                    f"[{name}] {lab}: recall slightly down "
                    f"{base_m['recall']:.3f} -> {m['recall']:.3f} (Δ={d_recall:+.3f})"
                )
            if d_prec < -0.05:
                warnings.append(
                    f"[{name}] {lab}: precision down "
                    f"{base_m['precision']:.3f} -> {m['precision']:.3f} (Δ={d_prec:+.3f})"
                )
            if d_f1 < -0.05:
                warnings.append(
                    f"[{name}] {lab}: F1 down "
                    f"{base_m['f1']:.3f} -> {m['f1']:.3f} (Δ={d_f1:+.3f})"
                )

    for w in warnings:
        print("WARN", w)
    if failures:
        print()
        for f in failures:
            print("FAIL", f)
        print(f"\n{len(failures)} regression(s) exceed --recall-tolerance "
              f"{args.recall_tolerance}")
        return 1
    print(f"OK ({len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
