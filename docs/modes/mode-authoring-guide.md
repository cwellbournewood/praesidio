# Mode Authoring Guide

This guide describes how to author a Praesidio **mode** — a signed, versioned
bundle that tunes detection, decision, anonymisation, vault behaviour, and UI
terminology for a specific vertical (healthcare, finance, legal, software,
defence, etc).

Modes are the primary extension surface for community and partner contributions
in regulated verticals. The baseline gateway ships three reference modes
(healthcare, finserv, software); everything else lands as a mode bundle.

## 1. File layout

```
modes/<mode-id>/
├── mode.yaml
├── entities.yaml
├── policy.yaml
├── compliance.map.yaml
├── vault.profile.yaml
├── ui.theme.json
└── eval.suite/
    ├── 01-*.json
    └── ...
```

All paths are relative to the mode root. The schema is enforced by
[`schema/mode.schema.json`](./schema/mode.schema.json) and validated at bundle
build time (`make bundle`).

## 2. `mode.yaml`

The manifest. One per mode.

```yaml
apiVersion: praesidio/v1
kind: Mode
metadata:
  id: healthcare              # lowercase, [a-z0-9-]+
  name: "Healthcare / Clinical"
  version: 0.1.0              # semver
  owner: privacy@example.org
  maintainers:
    - { name: "Jane Doe", email: "jane@example.org", org: "Example Health" }
  description: |
    HIPAA Safe-Harbor + GDPR Art.9 tuning. Designed for clinical assistants,
    discharge-summary drafting, and de-identification of PHI for analytics.
  homepage: https://praesidio.dev/modes/healthcare
  license: Apache-2.0
spec:
  extends: pii-strict          # baseline policy this mode layers on; or "none"
  compatible_overlays:
    - strict
    - productivity
    - research
  jurisdictions:               # which jurisdictions this mode is tuned for
    - US
    - EU
    - UK
  regulations:                 # high-level regs this mode supports
    - HIPAA
    - HITECH
    - GDPR-Art-9
    - NHS-DSPT
  risk_tier: high              # low | medium | high — drives default fail_mode
  includes:
    entities:   entities.yaml
    policy:     policy.yaml
    compliance: compliance.map.yaml
    vault:      vault.profile.yaml
    ui:         ui.theme.json
    eval:       eval.suite/
  signature:                   # populated by `cosign sign-bundle`
    keyref: ""
    digest: ""
```

## 3. `entities.yaml`

Declares the domain recognisers. Three sources are supported:

1. **Built-in Presidio recognisers** — reference by `presidio.<NAME>`.
2. **Regex recognisers** — declared inline with a confidence score.
3. **LLM-classifier prompts** — for context-sensitive entities (MNPI, privilege,
   adverse-event) where lexical patterns are insufficient.

```yaml
apiVersion: praesidio/v1
kind: Entities
spec:
  presidio:                    # enable + tune built-in recognisers
    - { id: PERSON,         threshold: 0.7 }
    - { id: LOCATION,       threshold: 0.8 }
    - { id: MEDICAL_LICENSE,threshold: 0.6 }

  regex:                       # custom regex recognisers
    - id: regex.mrn
      label: "Medical Record Number"
      pattern: '(?i)\bMRN[:\s#-]*([A-Z0-9]{6,12})\b'
      score: 0.85
      context: [chart, record, patient, admission]

    - id: regex.npi
      label: "National Provider Identifier"
      pattern: '\b\d{10}\b'
      score: 0.6              # low score — must be context-boosted
      context: [npi, provider, physician, ordering]

  classifiers:                 # LLM-judged entities
    - id: cls.adverse_event
      label: "Adverse Event"
      prompt_ref: prompts/adverse-event.md
      model: ollama/llama3.1-70b           # always on-prem for classifiers
      score_threshold: 0.75
      cache_ttl: 24h
```

**Score discipline.** Regex recognisers should declare a *base* score in the
0.5–0.7 range and rely on `context` words to boost — this is how Presidio
avoids over-firing on bare 10-digit numbers, MRN-shaped strings inside URLs,
etc. Reserve scores ≥ 0.85 for unambiguous patterns (e.g. anchored MRN with
prefix).

## 4. `policy.yaml`

A standard `kind: Policy` document (see
[`architecture/03-policy-engine.md`](../architecture/03-policy-engine.md)). The
mode's policy references entities declared in `entities.yaml` by their `id`.

Authoring rules:

- **Order findings by severity.** Block rules first (credential leaks, unblinding,
  classification spillage), then transforms, then `allow`.
- **Declare `fail_mode: closed`** for any mode with `risk_tier: high`.
- **Pin `route.upstream`** to a model whose `safety_certifications` include the
  mode's regulation (e.g. `BAA` for healthcare, `FedRAMP` for gov).
- **Use `scope: session`** for tokens that need to round-trip a single
  conversation; **`scope: tenant`** for tokens shared across a workspace.

## 5. `compliance.map.yaml`

Cross-reference each entity to the specific clause(s) of the regulations the
mode targets. This drives the **compliance report** view in the UI and the
auto-generated coverage matrix.

```yaml
apiVersion: praesidio/v1
kind: ComplianceMap
spec:
  mappings:
    - entity: regex.mrn
      clauses:
        - { reg: HIPAA, ref: "45 CFR §164.514(b)(2)(i)(H)", note: "Medical record numbers" }
        - { reg: GDPR,  ref: "Art. 9(1)",                   note: "Health data" }
    - entity: pii.person
      clauses:
        - { reg: HIPAA, ref: "45 CFR §164.514(b)(2)(i)(A)", note: "Names" }
        - { reg: GDPR,  ref: "Art. 4(1)",                   note: "Personal data" }
```

Coverage gaps are surfaced at build time: any clause listed in
`mode.yaml#spec.regulations` that has zero entity mappings produces a warning.

## 6. `vault.profile.yaml`

Vault behaviour for this mode — TTLs, re-identification scopes, break-glass
roles.

```yaml
apiVersion: praesidio/v1
kind: VaultProfile
spec:
  defaults:
    scope: session
    ttl: 30m
  per_entity:
    regex.mrn:           { scope: tenant,  ttl: 7d }
    pii.person:     { scope: session, ttl: 1h }
    cls.adverse_event:   { scope: tenant,  ttl: 30d, irreversible: true }

  reidentify:
    allowed_roles: ["clinician", "treating-physician"]
    require_purpose: true       # caller must declare treatment/payment/operations
    audit_severity: warning     # every re-ID writes a warning-level audit event

  break_glass:
    enabled: true
    allowed_roles: ["compliance-officer"]
    mfa_required: true
    max_duration: 15m
    auto_revoke: true
    notify: ["security@example.org", "privacy@example.org"]
```

## 7. `ui.theme.json`

Terminology and risk-language overrides. The UI uses these strings instead of
the generic defaults — "patient" instead of "subject" in healthcare, "matter"
instead of "case" in legal, etc.

```json
{
  "$schema": "../../docs/modes/schema/ui.theme.schema.json",
  "subject_noun":      "patient",
  "subject_noun_plural": "patients",
  "data_noun":         "PHI",
  "risk_tone":         "clinical",
  "severity_labels": {
    "critical": "Reportable breach",
    "high":     "Privacy incident",
    "medium":   "Disclosure risk",
    "low":      "Informational"
  },
  "callout_examples": {
    "block":      "Blocked: would expose protected health information.",
    "tokenise":   "Tokenised: patient identifier replaced for processing.",
    "redact":     "Redacted: identifier removed before egress.",
    "fpe":        "Format-preserved: synthetic identifier substituted."
  }
}
```

## 8. `eval.suite/`

Each file is a single test case in the same JSON shape as
`examples/demo-prompts/`. The eval runner (`make eval-mode MODE=healthcare`)
loads the mode, runs each prompt, and asserts that `decision.action` and
`decision.findings[*].label` match the `expected` block.

```json
{
  "name": "Discharge summary contains MRN and name",
  "input": {
    "messages": [
      { "role": "user", "content": "Draft discharge for John Doe, MRN 12345678, hypertension." }
    ]
  },
  "expected": {
    "action": "transform",
    "findings": [
      { "label": "regex.mrn",        "min_count": 1 },
      { "label": "pii.person",  "min_count": 1 }
    ],
    "egress_contains_none": ["John Doe", "12345678"]
  }
}
```

**Minimum eval coverage** for a mode to be marked `stable`:

- ≥ 1 prompt per declared entity (positive case)
- ≥ 3 negative prompts (no findings expected) to catch over-firing
- ≥ 1 prompt per `block`-action rule
- ≥ 1 prompt exercising the break-glass / re-identify flow

## 9. Signing and publishing

```bash
# Validate locally
make mode-validate MODE=healthcare

# Run eval suite
make eval-mode MODE=healthcare

# Sign and package
cosign sign-blob --key cosign.key \
  examples/policies/modes/healthcare/ \
  > examples/policies/modes/healthcare/mode.sig

# Publish to a mode registry (OCI artefact)
make mode-publish MODE=healthcare REGISTRY=ghcr.io/example/praesidio-modes
```

Modes are distributed as OCI artefacts. The gateway verifies the cosign
signature before loading; unsigned modes load only when
`PRAESIDIO_ALLOW_UNSIGNED_MODES=true` (dev-only).

## 10. Conformance checklist

A mode is **ready for community review** when:

- [ ] `mode.yaml` validates against `schema/mode.schema.json`
- [ ] Every entity in `policy.yaml` is declared in `entities.yaml`
- [ ] Every regulation in `mode.yaml#spec.regulations` has ≥ 1 mapping in `compliance.map.yaml`
- [ ] `vault.profile.yaml` declares break-glass roles if `risk_tier ≥ high`
- [ ] `ui.theme.json` overrides at least `subject_noun` and `data_noun`
- [ ] `eval.suite/` meets minimum coverage (§ 8)
- [ ] `make eval-mode MODE=<id>` passes at ≥ 95% accuracy on the suite
- [ ] `README.md` in the mode directory documents intended use and limitations

A mode is **ready for production** when it additionally:

- [ ] Has a signed bundle published to a verified registry
- [ ] Has been red-teamed against [`docs/redteam/playbook.md`](../redteam/playbook.md)
- [ ] Has a named maintainer who has reviewed it within 90 days
