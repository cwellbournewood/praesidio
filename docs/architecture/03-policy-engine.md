# 03 · Policy Engine & Policy-as-Code DSL

Policies are **YAML in git**. Every change is reviewed via pull request, signed
with cosign, packaged into a bundle (tarball), and pulled or pushed to gateways
which verify the signature before reloading. There is no live "edit a rule in
the UI and it takes effect" path — the UI generates a PR.

## Why YAML

Three options were on the table; see [ADR-0003](../adr/0003-policy-as-code.md).
We picked YAML + JSON-Schema validation because:
- security teams already write YAML for Falco, OPA Gatekeeper, Kyverno;
- it diff-reviews cleanly;
- it stays declarative — no Turing-complete CEL/Rego trap.

## Bundle layout

```
bundle/
├── manifest.yaml        version, signature, includes
├── policies/
│   ├── 0001-pii-strict.yaml
│   ├── 0002-code-protection.yaml
│   └── 0100-healthcare.yaml
├── models.yaml          model registry entries
├── routes.yaml          per-route bindings (path → policy id, upstream)
└── classifiers/
    └── intent.onnx      optional bundled classifier weights
```

## Schema (abbreviated)

```yaml
apiVersion: section/v1
kind: Policy
metadata:
  id: pii-strict
  name: "Strict PII anonymisation for marketing data"
  owner: data-protection@acme.com
  description: |
    All names, emails, phone numbers tokenised before reaching external models.
spec:
  match:                                # when does this policy apply?
    routes: ["/v1/chat/completions", "/v1/completions"]
    tenants: ["*"]
    principals:
      groups: ["marketing", "sales"]
    models: ["gpt-4o*", "claude-3-*"]
  detect:                               # which detectors run
    enable:
      - pii.email
      - pii.phone
      - financial.iban
      - pii.person
      - pii.location
      - secrets.aws
      - credential.generic_high_entropy
    thresholds:
      pii.person: 0.7              # confidence cutoff
  decide:                               # rules evaluated top-down, first match wins
    rules:
      - when: "any(findings, .label == 'secrets.aws')"
        action: block
        reason: "AWS credential leak attempt"
        severity: critical
      - when: "any(findings, .label in ['pii.email','pii.person','pii.phone'])"
        action: transform
        transforms:
          - { label: pii.email,     method: tokenise, scope: tenant, ttl: 1h }
          - { label: pii.person, method: tokenise, scope: tenant, ttl: 1h }
          - { label: pii.phone,     method: fpe }
          - { label: financial.iban,      method: redact, replacement: "[REDACTED_IBAN]" }
      - when: "true"
        action: allow
  route:                                # optional override of upstream
    when_jurisdiction: "EU"
    upstream: "azure-westeurope-gpt4o"
  fail_mode: closed
  audit:
    severity_min: info
    sinks: ["postgres", "splunk-hec"]
```

## Decision context

```python
DecisionContext = {
    "principal":     {user_id, tenant_id, groups, device_id, ip, country},
    "route":         "/v1/chat/completions",
    "model_request": {"provider": "openai", "model": "gpt-4o-mini"},
    "headers":       {... selected ...},
    "jurisdiction":  "EU" | "US" | ...,
    "time":          ISO-8601,
    "request_id":    UUIDv7,
}
```

## DSL expressions

A safe expression sublanguage based on
[CEL](https://github.com/google/cel-spec) (via `cel-python`) with the following
context-bound helpers:

```
findings           list[Finding]
principal          object
ctx                DecisionContext

any(coll, pred)
all(coll, pred)
count(coll, pred)
contains(s, sub)
matches(s, regex)
```

Examples:

```
count(findings, .label == 'pii.person') > 3
principal.country == 'DE' && ctx.model_request.provider != 'sovereign'
any(findings, .label in ['secrets.aws','secrets.gcp','secrets.azure'])
```

## Evaluator semantics

1. Build `DecisionContext` from request.
2. Run `match` block — if false, skip policy.
3. Run enabled detectors → `Findings[]`.
4. Walk `decide.rules` top-down. First rule whose `when` evaluates true wins.
5. If matched rule is `transform`, compose `Transform[]` and pass to anonymiser.
6. If `route` overrides upstream, swap before forwarding.
7. Write audit event with `policy_id`, `policy_version`, `rule_index`,
   `findings_hash`, `decision`.

## Simulation mode

Every policy can be loaded in **simulation** (alongside the active one). In
simulation, the gateway runs the policy against live traffic and writes
*shadow* audit events labelled `mode=simulate`, without enforcing. The UI shows
a diff: what would have changed vs. production. This is how policies are rolled
out — no surprise blocks.

## Staged rollout

Bundle manifest supports:

```yaml
canary:
  percentage: 5
  selectors:
    tenants: ["*"]
```

5% of traffic gets the new bundle; the rest stays on the previous version.
Canary scope is sticky per session to avoid flapping.
