#!/usr/bin/env python3
"""
Praesidio compliance report generator.

Reads the gateway's audit log directly from Postgres (read-only role) and
renders a Markdown + (optional) PDF report mapped to SOC 2 Common Criteria
and GDPR articles, using the canonical mappings in docs/compliance/.

Usage:
    uv run python scripts/compliance_report.py \\
        --tenant acme --days 90 \\
        --out dist/compliance/acme-2026-Q1

Outputs:
    <out>.md   — Markdown report (always written)
    <out>.pdf  — PDF rendered via WeasyPrint, if installed (best-effort)
    <out>.json — Raw aggregated metrics

Environment:
    DATABASE_URL          full DSN (psycopg2 / asyncpg-compatible). If unset,
                          PRAESIDIO_REPORT_DSN is consulted, then a default
                          read-only role on the local stack.
    PRAESIDIO_COMPLIANCE_DOCS  override path to docs/compliance/ (default:
                          ./docs/compliance)

Exit codes:
    0  success
    1  missing dependency / argument error
    2  database error
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore
except ImportError:
    psycopg2 = None  # type: ignore
    RealDictCursor = None  # type: ignore

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print(
        "ERROR: jinja2 not installed. Run: uv pip install jinja2 psycopg2-binary weasyprint",
        file=sys.stderr,
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "scripts" / "templates"
DEFAULT_DSN = "postgresql://praesidio_reporter:praesidio_reporter@localhost:5432/praesidio"


@dataclass
class Metrics:
    tenant: str
    period_start: str
    period_end: str
    total_events: int
    decisions: dict[str, int]
    severity: dict[str, int]
    findings_by_category: dict[str, int]
    block_rate: float
    transform_rate: float
    top_policies: list[dict[str, Any]]
    bundle_digests_seen: list[str]
    siem_egress_total: int
    siem_egress_failures: int
    detokenise_calls: int
    detokenise_unique_principals: int


SOC2_MAPPINGS = [
    ("CC6.1", "Logical access controls", "All admin actions require OIDC + RBAC; principal recorded in every audit row."),
    ("CC6.6", "Restrict access to information assets", "Anonymiser tokenises PII before upstream; detokenise audited and rate-limited."),
    ("CC7.2", "Monitoring of system components", "Gateway /metrics + Tempo traces + Loki logs; dashboards in deploy/grafana/."),
    ("CC7.3", "Evaluating security events", "Findings categorised by severity; SIEM webhook for >= warning."),
    ("CC8.1", "Change management", "Policy bundles are signed and digest-pinned per audit row; reload audited."),
    ("CC9.1", "Risk identification", "Threat model maintained at docs/threat-model.md; STRIDE per component."),
]

GDPR_MAPPINGS = [
    ("Art. 5(1)(c)", "Data minimisation", "Anonymiser strips or tokenises identified entities before they reach upstream."),
    ("Art. 5(1)(e)", "Storage limitation", "Vault TTL <= 24h; audit retention per-tenant policy."),
    ("Art. 5(1)(f)", "Integrity and confidentiality", "TLS, AES-256-GCM vault, hash-chained audit."),
    ("Art. 25", "Data protection by design and by default", "Default fail-closed for restricted classes."),
    ("Art. 30", "Records of processing", "Audit log + policy bundle digest = RoPA evidence."),
    ("Art. 32", "Security of processing", "See threat-model.md."),
    ("Art. 33-34", "Breach notification", "Output DLP detects regurgitation; SIEM sink emits high-severity event."),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True, help="Tenant ID to scope the report to.")
    p.add_argument("--days", type=int, default=90, help="Number of days back from now (default: 90).")
    p.add_argument("--out", type=Path, default=Path("dist/compliance/report"),
                   help="Output path prefix (no extension).")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL")
                   or os.environ.get("PRAESIDIO_REPORT_DSN") or DEFAULT_DSN,
                   help="Postgres DSN (default: from env / read-only role).")
    p.add_argument("--no-pdf", action="store_true",
                   help="Skip PDF rendering even if weasyprint is installed.")
    return p.parse_args()


def fetch_metrics(dsn: str, tenant: str, days: int) -> Metrics:
    if psycopg2 is None:
        print("ERROR: psycopg2 not installed.", file=sys.stderr)
        sys.exit(1)

    end = dt.datetime.now(tz=dt.UTC)
    start = end - dt.timedelta(days=days)

    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
    except psycopg2.Error as e:
        print(f"ERROR: cannot connect to Postgres ({dsn}): {e}", file=sys.stderr)
        sys.exit(2)

    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                """,
                (tenant, start, end),
            )
            total = int(cur.fetchone()["n"])

            cur.execute(
                """
                SELECT decision, count(*) AS n
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                GROUP BY decision
                """,
                (tenant, start, end),
            )
            decisions = {r["decision"]: int(r["n"]) for r in cur.fetchall()}

            cur.execute(
                """
                SELECT severity, count(*) AS n
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                GROUP BY severity
                """,
                (tenant, start, end),
            )
            severity = {r["severity"]: int(r["n"]) for r in cur.fetchall()}

            cur.execute(
                """
                SELECT f.category, count(*) AS n
                FROM audit_events e
                JOIN LATERAL jsonb_array_elements(e.findings) AS fj(value) ON TRUE
                JOIN LATERAL jsonb_to_record(fj.value) AS f(category text) ON TRUE
                WHERE e.tenant_id = %s AND e.created_at >= %s AND e.created_at < %s
                GROUP BY f.category
                ORDER BY n DESC
                """,
                (tenant, start, end),
            )
            findings = {r["category"]: int(r["n"]) for r in cur.fetchall() if r["category"]}

            cur.execute(
                """
                SELECT policy_name, decision, count(*) AS n
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                  AND policy_name IS NOT NULL
                GROUP BY policy_name, decision
                ORDER BY n DESC
                LIMIT 20
                """,
                (tenant, start, end),
            )
            top_policies = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT bundle_digest
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                  AND bundle_digest IS NOT NULL
                """,
                (tenant, start, end),
            )
            digests = sorted({r["bundle_digest"] for r in cur.fetchall()})

            cur.execute(
                """
                SELECT
                  count(*) FILTER (WHERE status = 'delivered') AS ok,
                  count(*) FILTER (WHERE status <> 'delivered') AS failed
                FROM audit_egress
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                """,
                (tenant, start, end),
            )
            egress = cur.fetchone() or {}

            cur.execute(
                """
                SELECT count(*) AS total, count(DISTINCT principal_sub) AS principals
                FROM audit_events
                WHERE tenant_id = %s AND created_at >= %s AND created_at < %s
                  AND event_type = 'admin.detokenise'
                """,
                (tenant, start, end),
            )
            detok = cur.fetchone() or {}
    finally:
        conn.close()

    block = decisions.get("block", 0)
    transform = decisions.get("transform", 0)
    return Metrics(
        tenant=tenant,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        total_events=total,
        decisions=decisions,
        severity=severity,
        findings_by_category=findings,
        block_rate=(block / total) if total else 0.0,
        transform_rate=(transform / total) if total else 0.0,
        top_policies=top_policies,
        bundle_digests_seen=digests,
        siem_egress_total=int((egress.get("ok") or 0) + (egress.get("failed") or 0)),
        siem_egress_failures=int(egress.get("failed") or 0),
        detokenise_calls=int(detok.get("total") or 0),
        detokenise_unique_principals=int(detok.get("principals") or 0),
    )


def render(metrics: Metrics) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(disabled_extensions=("md", "j2")),
        keep_trailing_newline=True,
    )
    template = env.get_template("compliance_report.md.j2")
    return template.render(
        m=metrics,
        soc2=SOC2_MAPPINGS,
        gdpr=GDPR_MAPPINGS,
        generated_at=dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
    )


def maybe_render_pdf(md_path: Path, pdf_path: Path) -> None:
    try:
        from weasyprint import HTML  # type: ignore
        import markdown  # type: ignore
    except ImportError:
        print("   (skipping PDF — install weasyprint + markdown for PDF output)")
        return
    html = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables"])
    css = "body{font-family:Geist,system-ui,sans-serif;max-width:900px;margin:2em auto;color:#1a1b1f} h1,h2,h3{color:#3730a3} table{border-collapse:collapse;width:100%} th,td{border:1px solid #ddd;padding:6px 10px} th{background:#f5f5f1}"
    full = f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{html}</body></html>"
    HTML(string=full).write_pdf(str(pdf_path))
    print(f"   pdf -> {pdf_path}")


def main() -> int:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    print(f":: fetching audit metrics for tenant={args.tenant} days={args.days}")
    metrics = fetch_metrics(args.dsn, args.tenant, args.days)
    print(f"   {metrics.total_events} event(s) in window")

    md = render(metrics)
    md_path = args.out.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    print(f"   markdown -> {md_path}")

    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")
    print(f"   metrics  -> {json_path}")

    if not args.no_pdf:
        pdf_path = args.out.with_suffix(".pdf")
        maybe_render_pdf(md_path, pdf_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
