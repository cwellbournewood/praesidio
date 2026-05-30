"""Policy engine.

Walks the active bundle for the request's route, picks the first policy whose
`match` block applies, and evaluates `decide.rules` top-down, first-match-wins.
"""
from __future__ import annotations

import fnmatch
import logging
from collections.abc import Iterable

from .dsl import compile_predicate
from .loader import PolicyBundle
from .models import (
    Decision,
    DecisionContext,
    Finding,
    Policy,
    PrincipalCtx,
    Transform,
)

_log = logging.getLogger(__name__)


def _glob_any(needle: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(needle, p) for p in patterns)


def _principal_matches(spec: dict, principal: PrincipalCtx) -> bool:
    if not spec:
        return True
    if "groups" in spec:
        req = set(spec["groups"])
        if not req.intersection(set(principal.groups)):
            return False
    if "tenants" in spec:
        if not _glob_any(principal.tenant_id, spec["tenants"]):
            return False
    if "country" in spec:
        if principal.country != spec["country"]:
            return False
    return True


def policy_applies(policy: Policy, ctx: DecisionContext) -> bool:
    m = policy.spec.match
    if not _glob_any(ctx.route, m.routes):
        return False
    if not _glob_any(ctx.principal.tenant_id, m.tenants):
        return False
    if m.models and ctx.model_request.model:
        if not _glob_any(ctx.model_request.model, m.models):
            return False
    return _principal_matches(m.principals, ctx.principal)


def _findings_for_dsl(findings: list[Finding]) -> list[dict]:
    """CEL/DSL-friendly view; `.label`, `.detector`, etc."""
    return [f.model_dump() for f in findings]


def _expand_transforms(rule_transforms: list[Transform], findings: list[Finding]) -> list[Transform]:
    """Resolve wildcard `label: '*'` into one Transform per distinct finding label."""
    labels_in_findings = {f.label for f in findings}
    out: list[Transform] = []
    for t in rule_transforms:
        if t.label == "*":
            for lbl in labels_in_findings:
                out.append(t.model_copy(update={"label": lbl}))
        else:
            out.append(t)
    return out


def evaluate(
    bundle: PolicyBundle,
    ctx: DecisionContext,
    findings: list[Finding],
) -> Decision:
    """Run the policy engine. Returns a Decision (never raises on bad rules)."""
    env_base = {
        "findings": _findings_for_dsl(findings),
        "principal": ctx.principal.model_dump(),
        "ctx": ctx.model_dump(mode="json"),
    }
    for policy in bundle.policies:
        if not policy_applies(policy, ctx):
            continue
        spec = policy.spec
        for idx, rule in enumerate(spec.decide.rules):
            try:
                pred = compile_predicate(rule.when)
                hit = bool(pred.evaluate(env_base))
            except Exception:
                _log.exception(
                    "policy %s rule %d failed to evaluate; treating as no-match",
                    policy.metadata.id,
                    idx,
                )
                hit = False
            if not hit:
                continue
            transforms = (
                _expand_transforms(rule.transforms, findings)
                if rule.action == "transform"
                else []
            )
            upstream_override = spec.route.upstream if spec.route and spec.route.upstream else None
            return Decision(
                action=rule.action,
                transforms=transforms,
                policy_id=policy.metadata.id,
                policy_version=policy.metadata.version,
                rule_index=idx,
                reason=rule.reason,
                severity=rule.severity,
                fail_mode=spec.fail_mode,
                upstream_override=upstream_override,
                sinks=spec.audit.sinks,
                mode=spec.mode,
            )
    return Decision.allow_default()
