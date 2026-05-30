"""DLP coverage evaluation.

Drives every committed corpus through ``section_gateway.dlp.pipeline.run_pipeline``
in-process (no HTTP), then computes per-detector precision / recall / F1
using **label-presence** matching:

  * For each example, the ground-truth label set is ``set(spans[*].label)``
    (or ``set(labels)`` for the secrets / redteam corpora that don't have
    spans).
  * The predicted label set is ``set(finding.label for finding in result)``.
  * A true positive for label L on row R is: L is in BOTH sets.
  * A false positive for label L on row R is: L is in predicted but NOT
    in ground truth.
  * A false negative for label L on row R is: L is in ground truth but
    NOT in predicted.

Span-exact matching is intentionally avoided — hand-labelled offsets are
brittle, and the DLP gateway's downstream consumers care about *which*
sensitive categories were present, not pixel-perfect spans.

Outputs:

  * ``bench/eval/results/<utc>.json`` — full numerical breakdown
  * ``docs/benchmarks/coverage.md``    — human-readable per-detector table
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPORA_DIR = REPO_ROOT / "bench" / "eval" / "corpora"
RESULTS_DIR = REPO_ROOT / "bench" / "eval" / "results"
BASELINE_PATH = REPO_ROOT / "bench" / "eval" / "baseline.json"
DOCS_PATH = REPO_ROOT / "docs" / "benchmarks" / "coverage.md"

# Make the gateway package importable.
sys.path.insert(0, str(REPO_ROOT / "services" / "gateway"))


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------


@dataclass
class Example:
    id: str
    text: str
    truth_labels: set[str]
    corpus: str


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _load_corpus(name: str, path: Path) -> list[Example]:
    out: list[Example] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "spans" in row:
                truth = {s["label"] for s in row["spans"]}
            else:
                truth = set(row.get("labels", []))
            out.append(Example(id=row["id"], text=row["text"],
                               truth_labels=truth, corpus=name))
    return out


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def _predict(text: str, enable: list[str]) -> set[str]:
    from section_gateway.dlp.pipeline import run_pipeline
    result = await run_pipeline(text, enable=enable, deadline_s=2.0)
    return {f.label for f in result.findings}


# Which labels each corpus expects the pipeline to consider. We enable
# every detector family that could be relevant for the corpus, but score
# per-label as before.
_CORPUS_ENABLE: dict[str, list[str]] = {
    "presidio_sample": [
        "pii.email", "pii.phone", "financial.credit_card", "financial.iban",
        "pii.us_ssn", "network.ipv4",
        "pii.person", "pii.location", "pii.email",
        "pii.phone", "financial.credit_card", "financial.iban",
        "network.ip_address", "pii.us_ssn", "pii.date",
        "healthcare.medical_license",
    ],
    "secrets": [
        "credential.aws_access_key", "credential.aws_secret_key",
        "credential.github_pat", "credential.openai_api_key", "credential.anthropic_api_key",
        "credential.slack_bot_token", "credential.gcp_service_account",
        "credential.azure_storage_key", "credential.private_key",
        "credential.stripe_api_key", "credential.generic_high_entropy", "credential.jwt",
    ],
    "redteam": [
        "behavior.injection_ignore_previous",
        "behavior.injection_role_swap",
        "behavior.injection_jailbreak",
        "behavior.injection_system_override",
        "behavior.injection_prompt_exfil",
        "behavior.injection_base64_tool_abuse",
    ],
}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class LabelStats:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    support: int = 0  # rows where label is in ground truth

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0


async def _score_corpus(name: str, path: Path) -> dict[str, Any]:
    examples = _load_corpus(name, path)
    enable = _CORPUS_ENABLE[name]
    labels_of_interest = set(enable)

    stats: dict[str, LabelStats] = {l: LabelStats() for l in labels_of_interest}
    row_results: list[dict[str, Any]] = []

    # Run sequentially for deterministic ordering; the pipeline is
    # already concurrent across detectors internally.
    for ex in examples:
        predicted = await _predict(ex.text, enable)
        truth = ex.truth_labels & labels_of_interest

        for lab in labels_of_interest:
            in_truth = lab in truth
            in_pred = lab in predicted
            s = stats[lab]
            if in_truth:
                s.support += 1
            if in_truth and in_pred:
                s.tp += 1
            elif in_pred and not in_truth:
                s.fp += 1
            elif in_truth and not in_pred:
                s.fn += 1

        row_results.append({
            "id": ex.id,
            "truth": sorted(truth),
            "predicted": sorted(predicted & labels_of_interest),
            "extra_predicted": sorted(predicted - labels_of_interest),
        })

    per_label = {
        lab: {
            "tp": s.tp, "fp": s.fp, "fn": s.fn,
            "support": s.support,
            "precision": round(s.precision, 4),
            "recall": round(s.recall, 4),
            "f1": round(s.f1, 4),
        }
        for lab, s in sorted(stats.items())
    }

    # Micro-averaged (sum tp / fp / fn across labels)
    tp = sum(s.tp for s in stats.values())
    fp = sum(s.fp for s in stats.values())
    fn = sum(s.fn for s in stats.values())
    micro = LabelStats(tp=tp, fp=fp, fn=fn)

    return {
        "corpus": name,
        "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "sha256": _sha256_file(path),
        "n_examples": len(examples),
        "labels_evaluated": sorted(labels_of_interest),
        "per_label": per_label,
        "micro": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(micro.precision, 4),
            "recall": round(micro.recall, 4),
            "f1": round(micro.f1, 4),
        },
        "rows": row_results,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _write_markdown(report: dict[str, Any]) -> None:
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Section DLP — coverage matrix",
        "",
        f"_Last run: {report['started_utc']}_",
        "",
        "Per-detector precision / recall / F1, using **label-presence**",
        "scoring (does the pipeline raise the expected label set for each",
        "example?). Span-exact accuracy is reported separately in the JSON",
        "artefact (`bench/eval/results/<utc>.json`) under the `rows` key.",
        "",
        "## Corpus checksums",
        "",
        "| Corpus | examples | sha256 |",
        "|---|---:|---|",
    ]
    for c in report["corpora"]:
        lines.append(f"| `{c['path']}` | {c['n_examples']} | `{c['sha256'][:16]}…` |")
    lines.append("")

    for c in report["corpora"]:
        lines += [
            f"## Corpus: `{c['corpus']}`",
            "",
            f"Micro-averaged: precision={c['micro']['precision']:.3f}, "
            f"recall={c['micro']['recall']:.3f}, F1={c['micro']['f1']:.3f} "
            f"(tp={c['micro']['tp']}, fp={c['micro']['fp']}, fn={c['micro']['fn']})",
            "",
            "| label | support | tp | fp | fn | precision | recall | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for lab, s in c["per_label"].items():
            lines.append(
                f"| `{lab}` | {s['support']} | {s['tp']} | {s['fp']} | {s['fn']} | "
                f"{s['precision']:.3f} | {s['recall']:.3f} | {s['f1']:.3f} |"
            )
        lines.append("")

    lines += [
        "## How to reproduce",
        "",
        "```bash",
        "make eval                                   # full eval + regen this page",
        "python bench/eval/run_eval.py               # same, explicit",
        "python bench/eval/regression-check.py       # diff latest vs baseline",
        "```",
        "",
        "## Regression policy",
        "",
        "`bench/eval/regression-check.py` fails CI when any per-label",
        "**recall** drops more than 5 percentage points vs the committed",
        "`bench/eval/baseline.json`. Precision regressions are reported but",
        "do not gate the build (operators tune confidence thresholds in",
        "their own policies).",
        "",
    ]
    DOCS_PATH.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run() -> dict[str, Any]:
    corpora_files = [
        ("presidio_sample", CORPORA_DIR / "presidio_sample.jsonl"),
        ("secrets", CORPORA_DIR / "secrets.jsonl"),
        ("redteam", CORPORA_DIR / "redteam.jsonl"),
    ]
    corpora_results = []
    for name, path in corpora_files:
        print(f"[eval] {name}: {path}")
        c = await _score_corpus(name, path)
        print(f"[eval]   micro P={c['micro']['precision']:.3f} "
              f"R={c['micro']['recall']:.3f} F1={c['micro']['f1']:.3f}")
        corpora_results.append(c)

    return {
        "schema": 1,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "corpora": corpora_results,
    }


def _summarise_for_baseline(report: dict[str, Any]) -> dict[str, Any]:
    """Strip per-row detail, keep only per-label metrics."""
    out = {
        "schema": 1,
        "captured_utc": report["started_utc"],
        "corpora": {},
    }
    for c in report["corpora"]:
        out["corpora"][c["corpus"]] = {
            "sha256": c["sha256"],
            "n_examples": c["n_examples"],
            "micro": c["micro"],
            "per_label": c["per_label"],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Section DLP eval")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Overwrite bench/eval/baseline.json with this run's numbers")
    parser.add_argument("--no-docs", action="store_true",
                        help="Skip writing docs/benchmarks/coverage.md")
    args = parser.parse_args()

    report = asyncio.run(_run())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[eval] results -> {out}")

    if args.update_baseline:
        baseline = _summarise_for_baseline(report)
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        print(f"[eval] baseline -> {BASELINE_PATH}")

    if not args.no_docs:
        _write_markdown(report)
        print(f"[eval] docs    -> {DOCS_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
