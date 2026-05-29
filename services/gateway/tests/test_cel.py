"""DSL expression evaluator tests (`any` / `count` / `matches` / `in`)."""
from __future__ import annotations

from praesidio_gateway.policy.dsl import evaluate


def _findings(*labels):
    return [{"label": lbl, "detector": lbl.split(".", 1)[0], "confidence": 1.0} for lbl in labels]


def test_any_with_dotted_predicate():
    out = evaluate(
        "any(findings, .label == 'pii.email')",
        findings=_findings("pii.email", "pii.phone"),
    )
    assert out is True


def test_count_above_threshold():
    out = evaluate(
        "count(findings, .label == 'pii.person') > 1",
        findings=_findings("pii.person", "pii.person", "pii.email"),
    )
    assert out is True


def test_in_operator_on_list():
    out = evaluate(
        "any(findings, .label in ['secrets.aws','secrets.gcp'])",
        findings=_findings("secrets.gcp"),
    )
    assert out is True


def test_matches_helper():
    out = evaluate("matches(principal.user_id, '^u_')",
                   findings=[], principal={"user_id": "u_123"})
    assert out is True


def test_true_literal_always_fires():
    assert evaluate("true", findings=[]) is True


def test_and_or_precedence():
    assert evaluate("true && false || true", findings=[]) is True
    assert evaluate("false && (true || false)", findings=[]) is False


def test_country_in_list_via_principal():
    out = evaluate(
        "principal.country in ['DE','FR','IT']",
        findings=[], principal={"country": "DE"},
    )
    assert out is True


def test_all_with_predicate():
    out = evaluate(
        "all(findings, .confidence > 0.5)",
        findings=_findings("pii.email", "pii.phone"),
    )
    assert out is True
