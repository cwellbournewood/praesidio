# ADR-0003 · Policy-as-code in YAML + CEL

Date: 2026-05-27 · Status: Accepted

## Context

Three policy DSL approaches: a Turing-complete language (Rego, Starlark),
declarative YAML with a sublanguage for conditions (CEL), or a UI-driven
rule builder backed by a JSON document.

## Decision

YAML for structure, **CEL for conditions**. Validated against a published
JSON Schema. UI generates PRs against a git-tracked bundle; the gateway
verifies a cosign signature on the bundle before reloading.

## Consequences

- ➕ Diff-reviewable, git-native, familiar to platform teams.
- ➕ CEL is small, safe, fast, sandboxed; no eval-injection class.
- ➖ Less expressive than Rego — by design. Anything that needs more is
  expressed as a custom detector, not a policy rule.
