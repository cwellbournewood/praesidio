"""Policy engine: load a yaml policy, evaluate, assert decision + ordering."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from section_gateway.policy.engine import evaluate
from section_gateway.policy.loader import PolicyBundle
from section_gateway.policy.models import (
    DecisionContext,
    Finding,
    ModelRequestCtx,
    Policy,
    PrincipalCtx,
)

POLICY_DIR = Path(__file__).resolve().parents[3] / "examples" / "policies" / "policies"


def _load_policy(name: str) -> Policy:
    return Policy.model_validate(yaml.safe_load((POLICY_DIR / name).read_text()))


def _ctx() -> DecisionContext:
    return DecisionContext(
        principal=PrincipalCtx(user_id="u", tenant_id="default", groups=["engineering"]),
        route="/v1/chat/completions",
        model_request=ModelRequestCtx(provider="openai", model="gpt-4o-mini"),
        time=datetime.now(UTC),
        request_id="req-x",
    )


def _bundle(*policies: Policy) -> PolicyBundle:
    return PolicyBundle(digest="d", policies=list(policies))


def _finding(label: str, **kw) -> Finding:
    return Finding(
        id="01", label=label, start=0, end=5,
        text_hash="a" * 64, confidence=0.9, detector=label.split(".", 1)[0],
        **kw,
    )


def test_pii_strict_block_on_secret():
    pol = _load_policy("0001-pii-strict.yaml")
    bundle = _bundle(pol)
    findings = [_finding("secrets.aws")]
    dec = evaluate(bundle, _ctx(), findings)
    assert dec.action == "block"
    assert dec.rule_index == 0
    assert dec.severity == "critical"


def test_pii_strict_transform_on_email():
    pol = _load_policy("0001-pii-strict.yaml")
    bundle = _bundle(pol)
    findings = [_finding("pii.email")]
    dec = evaluate(bundle, _ctx(), findings)
    assert dec.action == "transform"
    assert any(t.label == "pii.email" and t.method == "tokenise" for t in dec.transforms)


def test_pii_strict_allow_when_clean():
    pol = _load_policy("0001-pii-strict.yaml")
    bundle = _bundle(pol)
    dec = evaluate(bundle, _ctx(), [])
    # Should match the final `when: "true"` allow rule.
    assert dec.action == "allow"


def test_first_match_wins_block_short_circuits_transform():
    """If both block and transform predicates are true, block must fire."""
    pol = _load_policy("0001-pii-strict.yaml")
    bundle = _bundle(pol)
    findings = [_finding("secrets.aws"), _finding("pii.email")]
    dec = evaluate(bundle, _ctx(), findings)
    assert dec.action == "block"


def test_no_applicable_policy_defaults_allow():
    bundle = _bundle()
    dec = evaluate(bundle, _ctx(), [])
    assert dec.action == "allow"
    assert dec.policy_id is None
