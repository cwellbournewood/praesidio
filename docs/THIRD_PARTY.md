# Third-party software

Praesidio is built on a stack of open-source components. This document
lists the third-party libraries and tools we depend on, their licenses,
their purpose in Praesidio, and their upstream URLs.

Versions are pinned in `services/gateway/pyproject.toml` and
`services/ui/package.json`. License strings are taken from the most
recent published metadata on PyPI / npm at the time of writing and may
drift; the file `LICENSE` of each upstream package is the authoritative
source.

## Gateway (Python)

| Name | License | Purpose | Upstream |
|---|---|---|---|
| fastapi | MIT | HTTP framework for the gateway API | https://github.com/tiangolo/fastapi |
| uvicorn | BSD-3-Clause | ASGI server | https://github.com/encode/uvicorn |
| httpx | BSD-3-Clause | Async HTTP client for upstream LLM calls | https://github.com/encode/httpx |
| pydantic | MIT | Request / policy model validation | https://github.com/pydantic/pydantic |
| pydantic-settings | MIT | Env + file settings loader | https://github.com/pydantic/pydantic-settings |
| sqlalchemy | MIT | Database ORM / Core | https://github.com/sqlalchemy/sqlalchemy |
| asyncpg | Apache-2.0 | Async Postgres driver | https://github.com/MagicStack/asyncpg |
| redis (redis-py) | MIT | Redis client for the token vault | https://github.com/redis/redis-py |
| pyyaml | MIT | Policy bundle parser | https://github.com/yaml/pyyaml |
| cel-python | Apache-2.0 | CEL expressions inside policy DSL | https://github.com/cloud-custodian/cel-python |
| cryptography | Apache-2.0 OR BSD-3-Clause | Symmetric crypto for the vault + envelope keys | https://github.com/pyca/cryptography |
| structlog | Apache-2.0 OR MIT | Structured JSON logging | https://github.com/hynek/structlog |
| prometheus-client | Apache-2.0 | `/metrics` endpoint | https://github.com/prometheus/client_python |
| opentelemetry-api | Apache-2.0 | Tracing API | https://github.com/open-telemetry/opentelemetry-python |
| opentelemetry-sdk | Apache-2.0 | Tracing SDK | https://github.com/open-telemetry/opentelemetry-python |
| opentelemetry-instrumentation-fastapi | Apache-2.0 | Auto-instrumentation | https://github.com/open-telemetry/opentelemetry-python-contrib |
| opentelemetry-exporter-otlp | Apache-2.0 | OTLP/gRPC exporter | https://github.com/open-telemetry/opentelemetry-python |
| presidio-analyzer | MIT | PII / entity detection | https://github.com/microsoft/presidio |
| spacy | MIT | NLP backbone for Presidio | https://github.com/explosion/spaCy |
| detect-secrets | Apache-2.0 | Secret-pattern detector | https://github.com/Yelp/detect-secrets |
| ulid-py | Apache-2.0 | Sortable IDs for audit rows | https://github.com/ahawker/ulid |
| jsonschema | MIT | Policy + bundle schema validation | https://github.com/python-jsonschema/jsonschema |
| pytest | MIT | Test runner | https://github.com/pytest-dev/pytest |
| ruff | MIT | Lint + format | https://github.com/astral-sh/ruff |
| mypy | MIT | Static type checking | https://github.com/python/mypy |

## Admin UI (Node / TypeScript)

| Name | License | Purpose | Upstream |
|---|---|---|---|
| next | MIT | React framework / SSR | https://github.com/vercel/next.js |
| react | MIT | UI library | https://github.com/facebook/react |
| react-dom | MIT | DOM renderer | https://github.com/facebook/react |
| tailwindcss | MIT | Utility-first CSS | https://github.com/tailwindlabs/tailwindcss |
| lucide-react | ISC | Icon set | https://github.com/lucide-icons/lucide |
| swr | MIT | Data fetching / cache | https://github.com/vercel/swr |
| next-themes | MIT | Dark mode handling | https://github.com/pacocoursey/next-themes |
| @radix-ui/react-dialog | MIT | Accessible dialog primitive | https://github.com/radix-ui/primitives |
| @radix-ui/react-dropdown-menu | MIT | Accessible menus | https://github.com/radix-ui/primitives |
| @radix-ui/react-popover | MIT | Accessible popovers | https://github.com/radix-ui/primitives |
| @radix-ui/react-select | MIT | Accessible select | https://github.com/radix-ui/primitives |
| @radix-ui/react-slot | MIT | Composition slot primitive | https://github.com/radix-ui/primitives |
| @radix-ui/react-tabs | MIT | Accessible tabs | https://github.com/radix-ui/primitives |
| @radix-ui/react-toast | MIT | Toast notifications | https://github.com/radix-ui/primitives |
| @radix-ui/react-tooltip | MIT | Accessible tooltips | https://github.com/radix-ui/primitives |
| cmdk | MIT | Command palette | https://github.com/pacocoursey/cmdk |
| date-fns | MIT | Date formatting | https://github.com/date-fns/date-fns |
| clsx | MIT | className composition | https://github.com/lukeed/clsx |
| tailwind-merge | MIT | Conflict-aware Tailwind merge | https://github.com/dcastil/tailwind-merge |
| class-variance-authority | Apache-2.0 | Variant-driven className utility | https://github.com/joe-bell/cva |

## Container images / runtime

| Name | License | Purpose | Upstream |
|---|---|---|---|
| postgres (16-alpine) | PostgreSQL License | Audit / lineage store (dev compose) | https://www.postgresql.org |
| redis (7-alpine) | RSALv2 / SSPLv1 (Redis 7.4+); BSD-3-Clause (Redis <7.4) | Token vault (dev compose) | https://redis.io |

## Build / release tooling

| Name | License | Purpose | Upstream |
|---|---|---|---|
| uv | Apache-2.0 OR MIT | Python project + venv manager | https://github.com/astral-sh/uv |
| pnpm | MIT | Node package manager | https://github.com/pnpm/pnpm |
| docker buildx | Apache-2.0 | Container builds | https://github.com/docker/buildx |
| cosign | Apache-2.0 | Image signing (keyless via Sigstore) | https://github.com/sigstore/cosign |
| syft | Apache-2.0 | SBOM generation (CycloneDX) | https://github.com/anchore/syft |
| helm | Apache-2.0 | Kubernetes package manager | https://github.com/helm/helm |
| kubeconform | Apache-2.0 | K8s manifest schema validation | https://github.com/yannh/kubeconform |
| terraform | BSL-1.1 (>=1.6) | Infrastructure-as-code (stub modules) | https://github.com/hashicorp/terraform |

## Notes

- The redis container image moved from BSD-3-Clause to a dual RSALv2 /
  SSPLv1 license starting with Redis 7.4. If your distribution model
  requires permissive licensing, pin to an earlier tag or switch to a
  fork such as Valkey (BSD-3-Clause).
- Terraform's Business Source License restricts hosted-service use cases
  by competitors of HashiCorp; for OSS-only deployments, OpenTofu is a
  drop-in replacement under MPL-2.0.
- Presidio bundles spaCy models that have their own (typically MIT or
  CC-BY-SA) licenses depending on which model file is loaded. Verify per
  language pack.
