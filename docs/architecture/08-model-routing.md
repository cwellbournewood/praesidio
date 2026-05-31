# 08 · Model Registry & Routing

## Registry

The model registry is part of the policy bundle (`models.yaml`):

```yaml
apiVersion: section/v1
kind: ModelRegistry
spec:
  models:
    - id: openai/gpt-4o-mini
      provider: openai
      endpoint_ref: openai-prod
      jurisdiction: US
      training_provenance: "OpenAI proprietary, opt-out via DPA"
      retention: "30 days (vendor)"
      privacy: "no-train"
      safety_certifications: ["SOC2", "ISO27001"]
      risk_tier: medium
      cost_per_1k_in: 0.00015
      cost_per_1k_out: 0.0006

    - id: anthropic/claude-3-5-sonnet
      provider: anthropic
      endpoint_ref: anthropic-prod
      jurisdiction: US
      privacy: "no-train"
      safety_certifications: ["SOC2", "ISO27001", "HIPAA"]
      risk_tier: medium

    - id: azure/gpt-4o-eu
      provider: azure-openai
      endpoint_ref: azure-westeurope
      jurisdiction: EU
      privacy: "no-train, data residency EU"
      safety_certifications: ["SOC2", "ISO27001", "C5", "HDS"]
      risk_tier: low

    - id: ollama/llama3.1-70b
      provider: ollama
      endpoint_ref: ollama-onprem
      jurisdiction: on-prem
      privacy: "fully local"
      risk_tier: low

  blocked:
    - pattern: "*/grok-*"
      reason: "Not approved; pending DPA"

  endpoints:
    - id: openai-prod
      base_url: https://api.openai.com/v1
      auth: { type: env, var: OPENAI_API_KEY }
    - id: azure-westeurope
      base_url: ${AZURE_OPENAI_ENDPOINT}
      auth: { type: env, var: AZURE_OPENAI_API_KEY }
      api_version: 2024-10-21
```

## Routing rules

`routes.yaml` binds inbound paths/models to outbound choices, with optional
overrides driven by the decision context:

```yaml
apiVersion: section/v1
kind: Routes
spec:
  - inbound:
      path: /v1/chat/completions
      requested_model: "gpt-4o-mini"
    upstream: openai/gpt-4o-mini

  # If caller is in the EU, swap to the EU deployment automatically.
  - inbound:
      path: /v1/chat/completions
      requested_model: "gpt-4o-mini"
    when: "principal.country in ['DE','FR','IT','ES','NL','PL']"
    upstream: azure/gpt-4o-eu

  # If the request carries restricted-class findings, force local.
  - inbound:
      path: /v1/chat/completions
    when: "any(findings, .label == 'classification.restricted')"
    upstream: ollama/llama3.1-70b

  # Anthropic-shaped requests
  - inbound:
      path: /anthropic/v1/messages
    upstream: anthropic/claude-3-5-sonnet
```

Rules are evaluated in order, first match wins. The router emits a header
on outbound calls (`x-section-route`) identifying the chosen model so
downstream telemetry can correlate.

## Cost & latency steering

Optional `cost_budget` and `latency_budget` annotations on a rule cause the
router to prefer the cheapest / fastest healthy upstream within an
equivalence class:

```yaml
- inbound: { path: /v1/chat/completions, requested_model: "gpt-4o-mini" }
  equivalence_class: "tier-1-fast"
  cost_budget: { max_usd_per_request: 0.01 }
  latency_budget: { p95_ms: 1500 }
```

Equivalence classes are declared in the model registry. A health probe
runs every 30s against each endpoint and feeds the router's circuit
breaker.

## Visible-models filter

`GET /v1/models` returns the union of models the caller's policies allow.
This is how IDEs and SDKs that introspect for model lists "discover" the
right names without leaking the rest of the registry.
