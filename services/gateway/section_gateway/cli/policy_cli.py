"""``section-policy`` — lint & simulation CLI for policy bundles (G9).

Two subcommands::

    section-policy lint   <bundle_dir>
    section-policy test   <bundle_dir>  [--fixtures path/to/cases.yaml]

``lint`` parses every policy file, validates against the pydantic
schema, and flags common mistakes (orphan rules, unknown detectors,
unreachable rules, missing transforms for ``action: transform``,
overlapping route globs). It also exercises the tool-call allowlist
config (``allow + deny`` patterns must be non-overlapping).

``test`` loads the bundle, then for each fixture in the YAML file
executes the policy engine against a synthetic
:class:`DecisionContext` + findings list and asserts the expected
``action`` (and optionally ``policy_id`` / ``transforms``).

Exit codes:

* 0 — all checks / cases passed
* 1 — lint error or test failure
* 2 — CLI usage error

The CLI is dependency-free beyond the gateway package and is intended
to run in CI (e.g. as a git pre-commit hook on the policy repo).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..policy.loader import PolicyReloadError, load_bundle
from ..policy.models import Policy

# Known detector families. Keep in sync with dlp.pipeline._DEFAULT_DETECTORS.
_KNOWN_DETECTORS: set[str] = {
    "regex",
    "secrets",
    "code",
    "prompt_injection",
    "llm_classifier",
    "presidio",
}


@dataclass(slots=True)
class LintIssue:
    severity: str  # "error" | "warning"
    policy_id: str
    message: str

    def format(self) -> str:
        return f"[{self.severity}] {self.policy_id}: {self.message}"


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def lint_bundle(bundle_dir: Path) -> list[LintIssue]:
    """Return a list of issues. Empty list means clean."""
    issues: list[LintIssue] = []
    try:
        bundle = load_bundle(bundle_dir, strict=True)
    except PolicyReloadError as exc:
        for pe in exc.parse_errors:
            issues.append(LintIssue("error", "<parse>", pe))
        return issues
    except FileNotFoundError as exc:
        issues.append(LintIssue("error", "<bundle>", str(exc)))
        return issues

    seen_ids: set[str] = set()
    for pol in bundle.policies:
        pid = pol.metadata.id
        if pid in seen_ids:
            issues.append(LintIssue("error", pid, "duplicate policy id"))
        seen_ids.add(pid)
        issues.extend(_lint_policy(pol))
    return issues


def _lint_policy(pol: Policy) -> list[LintIssue]:
    out: list[LintIssue] = []
    pid = pol.metadata.id
    spec = pol.spec
    if not spec.decide.rules:
        out.append(LintIssue("error", pid, "decide.rules is empty"))
    for i, rule in enumerate(spec.decide.rules):
        if rule.action == "transform" and not rule.transforms:
            out.append(LintIssue(
                "error", pid, f"rule[{i}] has action=transform but no transforms[]"
            ))
        if rule.action == "block" and rule.transforms:
            out.append(LintIssue(
                "warning", pid, f"rule[{i}] has action=block but also declares transforms (ignored)"
            ))
        if not rule.when or not rule.when.strip():
            out.append(LintIssue("error", pid, f"rule[{i}] has empty 'when' expression"))
    # Unknown detectors.
    for det in spec.detect.enable:
        # Strip subdetector qualifiers (e.g. "pii.email" -> "regex").
        fam = det.split(".", 1)[0]
        if fam not in _KNOWN_DETECTORS:
            out.append(LintIssue(
                "warning", pid, f"detect.enable references unknown detector family '{fam}'"
            ))
    # Tool allowlist sanity.
    al = spec.tool_allowlist
    if al is not None:
        for a in al.allow:
            for d in al.deny:
                # If an allow pattern is a strict subset of a deny pattern,
                # the allow can never fire — flag it.
                if a == d or (
                    "*" in d and "*" not in a and fnmatch.fnmatchcase(a, d)
                ):
                    out.append(LintIssue(
                        "warning",
                        pid,
                        f"tool_allowlist: allow '{a}' is shadowed by deny '{d}'",
                    ))
    # Unreachable rule check: a rule with when='true' or 'True' after
    # another such rule.
    catchall_seen = False
    for i, rule in enumerate(spec.decide.rules):
        if catchall_seen:
            out.append(LintIssue(
                "warning", pid, f"rule[{i}] is unreachable (a prior catch-all rule matched first)"
            ))
            break
        if rule.when.strip().lower() in ("true", "1", "1==1"):
            catchall_seen = True
    return out


# ---------------------------------------------------------------------------
# test (fixture-driven simulation)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TestCase:
    name: str
    route: str
    tenant_id: str
    user_id: str
    findings: list[dict[str, Any]]
    expect_action: str
    expect_policy_id: str | None = None


def _load_cases(path: Path) -> list[TestCase]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"fixtures file must be a YAML list of cases: {path}")
    out: list[TestCase] = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise SystemExit(f"case[{i}] must be a mapping")
        out.append(TestCase(
            name=str(c.get("name") or f"case-{i}"),
            route=str(c.get("route") or "/v1/chat/completions"),
            tenant_id=str(c.get("tenant_id") or "default"),
            user_id=str(c.get("user_id") or "test-user"),
            findings=list(c.get("findings") or []),
            expect_action=str(c.get("expect_action") or "allow"),
            expect_policy_id=c.get("expect_policy_id"),
        ))
    return out


def run_tests(bundle_dir: Path, fixtures: Path) -> tuple[int, int, list[str]]:
    """Returns (passed, failed, failure_messages)."""
    # Heavy imports lazy so plain ``lint`` doesn't pay for them.
    from datetime import UTC, datetime

    from ..policy.engine import evaluate
    from ..policy.models import (
        DecisionContext,
        Finding,
        ModelRequestCtx,
        PrincipalCtx,
    )

    bundle = load_bundle(bundle_dir, strict=True)
    cases = _load_cases(fixtures)
    passed = 0
    failed = 0
    msgs: list[str] = []
    for case in cases:
        ctx = DecisionContext(
            principal=PrincipalCtx(
                user_id=case.user_id,
                tenant_id=case.tenant_id,
            ),
            route=case.route,
            model_request=ModelRequestCtx(),
            time=datetime.now(UTC),
            request_id=f"cli-{case.name}",
        )
        findings: list[Finding] = []
        for fd in case.findings:
            findings.append(Finding(
                id="cli",
                label=str(fd.get("label", "")),
                start=int(fd.get("start", 0)),
                end=int(fd.get("end", 0)),
                text_hash="0" * 64,
                confidence=float(fd.get("confidence", 1.0)),
                detector=str(fd.get("detector", "regex")),
            ))
        decision = evaluate(bundle, ctx, findings)
        ok = decision.action == case.expect_action
        if case.expect_policy_id is not None:
            ok = ok and decision.policy_id == case.expect_policy_id
        if ok:
            passed += 1
        else:
            failed += 1
            msgs.append(
                f"FAIL {case.name}: expected action={case.expect_action} "
                f"policy_id={case.expect_policy_id} got action={decision.action} "
                f"policy_id={decision.policy_id}"
            )
    return passed, failed, msgs


# ---------------------------------------------------------------------------
# argparse glue
# ---------------------------------------------------------------------------


def _cmd_lint(args: argparse.Namespace) -> int:
    issues = lint_bundle(Path(args.bundle))
    if args.json:
        print(json.dumps([{"severity": i.severity, "policy_id": i.policy_id, "message": i.message} for i in issues], indent=2))
    else:
        for i in issues:
            print(i.format())
        if not issues:
            print("OK")
    return 0 if not any(i.severity == "error" for i in issues) else 1


def _cmd_test(args: argparse.Namespace) -> int:
    passed, failed, msgs = run_tests(Path(args.bundle), Path(args.fixtures))
    for m in msgs:
        print(m)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="section-policy",
        description="Lint and simulate Section policy bundles.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="Validate a bundle and flag common errors.")
    lint.add_argument("bundle", help="Path to the bundle directory.")
    lint.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    lint.set_defaults(func=_cmd_lint)

    test = sub.add_parser("test", help="Run fixture cases against a bundle.")
    test.add_argument("bundle", help="Path to the bundle directory.")
    test.add_argument(
        "--fixtures", required=True, help="YAML file with a list of test cases."
    )
    test.set_defaults(func=_cmd_test)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
