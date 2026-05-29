# Getting started

A five-minute happy path: bring up the full stack, run the demo, and
open the admin UI. Everything below has been wired into the
`quickstart` CI workflow — if these steps stop working, that workflow
goes red on the next PR.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| `git` | any recent | clone the repo |
| `docker` + `docker compose` | Docker Engine 24+ / Compose v2 | `compose v1` (the standalone binary) is unsupported |
| `bash` | 4+ | macOS users: the demo script also runs in Git Bash on Windows |
| `curl` | any | used by the demo script |

Nothing else is required for the quickstart — `uv`, `pnpm`, and
`make` are only needed for local source-level development.

## 1. Clone and copy the env template

```bash
git clone https://github.com/praesidio/praesidio.git
cd praesidio
cp .env.example .env
```

The defaults are fine for a local demo. You only need to edit `.env`
if you want to call a real upstream provider (set `OPENAI_API_KEY`
and/or `ANTHROPIC_API_KEY`). Without those, the gateway uses a
[built-in simulator](#about-the-simulator) so the demo still passes
end-to-end.

## 2. Bring up the stack

```bash
docker compose up --build -d
```

Compose starts four containers:

| Service | Port | Purpose |
|---|---|---|
| `postgres` | 5432 | audit log + lineage |
| `redis` | 6379 | token vault + cache |
| `gateway` | 8080 | inspection, policy, anonymisation |
| `ui` | 3000 | admin UI |

Wait ~15 seconds for the gateway healthcheck to flip green:

```bash
curl -fsS http://localhost:8080/healthz   # -> {"status":"ok"}
```

## 3. Run the end-to-end demo

```bash
bash scripts/demo.sh
```

You should see three test cases pass: a PII prompt is transformed
(tokenised), an AWS access key is blocked with an
`X-Praesidio-Reason` header, and an IBAN is redacted. The script
exits `0` on success and non-zero otherwise — that's the assertion
the [`quickstart` workflow](../.github/workflows/quickstart.yml) makes
on every pull request.

## 4. Open the admin UI

Browse to <http://localhost:3000>. You'll land on the dashboard. From
there:

- **Events** — every request the gateway processed, with severity,
  decision, and findings.
- **Policies** — the loaded bundle, with simulation diffs.
- **Simulator** — the [lane-B `/simulator` route](http://localhost:3000/simulator)
  for paste-and-test against the live gateway. The header carries a
  live indicator badge: green if the gateway is reachable, amber if
  the UI is using cached / mock data.
- **Tenants** — switch between demo tenants from the top-right.

## 5. Try the admin API directly (optional)

The gateway exposes a small admin surface (lane-A's
`praesidio-audit verify` CLI uses these too):

```bash
# Replay a stored prompt through current policy, without side effects
curl -X POST http://localhost:8080/admin/simulate \
  -H "Authorization: Bearer praesidio-demo-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"email me at jane@acme.com"}'

# Reverse a placeholder back to its original (privileged, audited)
curl -X POST http://localhost:8080/admin/detokenise \
  -H "Authorization: Bearer praesidio-demo-key" \
  -H "Content-Type: application/json" \
  -d '{"placeholder":"<EMAIL_a1b2>","reason":"investigation"}'

# Hot-reload the policy bundle
curl -X POST http://localhost:8080/admin/policy/reload \
  -H "Authorization: Bearer praesidio-demo-key"
```

## 6. Tear down

```bash
docker compose down -v   # -v drops the postgres + redis volumes
```

## About the simulator

When `OPENAI_API_KEY` is unset the gateway short-circuits the upstream
call and returns a deterministic stub completion (annotated with the
applied transforms). This keeps the quickstart and CI hermetic. The
demo script automatically relaxes its "expect HTTP 200 from upstream"
assertion in this mode and instead asserts only on the
`/admin/events` decision — see `scripts/demo.sh`.

## Where to next

- [Architecture overview](architecture/00-overview.md)
- [Threat model](threat-model.md)
- [Signed policy bundles](operations/signed-bundles.md)
- [OIDC integration](operations/oidc.md)
- [Observability stack](operations/observability.md)
