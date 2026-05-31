# Modes

A **mode** is a signed, versioned bundle that tunes Section for a specific
domain — healthcare, financial services, software engineering, intelligence,
and so on. A mode is not a separate runtime; it is a composable layer on top
of the standard gateway, anonymiser, and policy engine.

## What a mode contains

```
modes/<mode-id>/
├── mode.yaml              kind: Mode — manifest, version, includes, profile
├── entities.yaml          domain-specific recognisers and thresholds
├── policy.yaml            kind: Policy — decide rules referencing entities
├── compliance.map.yaml    entity → regulation clause cross-reference
├── vault.profile.yaml     tokenisation TTLs, scopes, break-glass roles
├── ui.theme.json          terminology and risk-language overrides
└── eval.suite/            gold-standard prompts + expected actions
    ├── 01-*.json
    └── ...
```

A mode is loaded by adding it to `manifest.yaml#spec.modes`. Modes are
applied **on top of** the baseline `pii-strict` policy unless the mode
declares `extends: none`.

## Composition

Modes compose with one or more **shape overlays**:

| Overlay        | Effect                                                                 |
|----------------|------------------------------------------------------------------------|
| `strict`       | Every detected entity defaults to redact; allow-list to expose         |
| `productivity` | Reversible tokenisation maximised; re-ID on trusted egress             |
| `public-egress`| Irreversible redaction only; no vault keys retained                    |
| `research`     | Synthetic surrogates (FF3-1 / LLM) preserving distribution             |
| `airgap`       | No external model calls; on-prem NER only; deterministic enclave tokens|

A typical deployment composes one vertical mode with one shape overlay:
`healthcare + strict` or `software + productivity`.

## See also

- [`mode-authoring-guide.md`](./mode-authoring-guide.md) — full schema + how to author
- [`schema/mode.schema.json`](./schema/mode.schema.json) — JSON Schema for validation
- [`../../examples/policies/modes/healthcare/`](../../examples/policies/modes/healthcare/) — reference implementation
