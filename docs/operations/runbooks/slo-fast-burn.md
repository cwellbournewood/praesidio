# Runbook — PraesidioFastBurn1h

**Severity**: page · **SLO**: `praesidio.chat.availability` · **Burn class**: fast

## What fired

The 5xx error rate on `/v1/chat/completions` is burning the 30-day error
budget at > 14.4× the sustainable rate, sustained over both the last 1h
and the last 5m windows. At this pace the entire 30d budget is consumed
in ~2 days.

## Likely causes (in order of frequency)

1. **Upstream provider outage** — OpenAI / Anthropic / Azure OpenAI /
   Bedrock returning 5xx. Praesidio surfaces these as 502 to the
   caller. Check the provider's status page.
2. **DLP pipeline crash loop** — a regex or Presidio recognizer
   raising on a new input pattern. Look for `dlp.pipeline` ERROR logs
   and `praesidio_detector_errors_total` spikes.
3. **Database degradation** — Postgres slow or the connection pool
   exhausted. Surfaces as `audit insert failed` ERROR lines.
4. **Bad release** — a new image was deployed within the last hour and
   the burn started shortly after.

## Triage (5 min)

1. **Confirm scope** — Grafana → *Praesidio · SLO* dashboard → look at
   the per-status break-out. If most 5xx are 502, suspect upstream.
   If 500, suspect the gateway.
2. **Check upstream** — `kubectl logs -l app=praesidio-gateway -c gateway -n praesidio --since=10m | grep -E "upstream|502"`.
3. **Recent deploys** — `kubectl rollout history deployment/praesidio-gateway -n praesidio`. If a release lines up with the alert start, **roll back**:
   `kubectl rollout undo deployment/praesidio-gateway -n praesidio`.

## Mitigation

| Cause | Action |
|---|---|
| Upstream provider | Switch traffic to a fallback model (edit `models.yaml`, `praesidio-audit verify` after); communicate ETA to customers; do not retry storm |
| DLP crash | Identify the offending detector via metrics; disable in the active policy (`detect.disable: [...]`); reload bundle |
| DB degradation | Scale Postgres / clear long-running queries; gateway will retry the audit queue from the local WAL |
| Bad release | Roll back to the prior tag; cut a hotfix branch |

## Communication

- Update the status page if customer-facing.
- Page the on-call platform engineer if mitigation > 30 min.

## Post-incident

- Open a `post-mortem/<date>-<short-title>.md` in the operations repo.
- Add a regression test or detector for the failure class.
- Verify the audit chain integrity for the alert window:
  `praesidio-audit verify --since 2h --dsn $DATABASE_URL`.
