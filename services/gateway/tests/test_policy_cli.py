"""section-policy CLI (G9).

Covers:
  * lint OK on a healthy bundle.
  * lint flags duplicate ids / empty rules / unknown detectors /
    transform-without-transforms / shadowed allowlist.
  * lint --json emits parseable JSON.
  * test runs fixtures and reports pass/fail correctly.
  * Exit codes: 0 on clean lint / all-passing tests, 1 on errors.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from section_gateway.cli.policy_cli import main


def _write_bundle(base: Path, policy_yaml: str, *, name: str = "0001.yaml") -> None:
    (base / "policies").mkdir(parents=True, exist_ok=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: section/v1\nkind: Bundle\n"
        "metadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (base / "models.yaml").write_text(
        "apiVersion: section/v1\nkind: ModelRegistry\nspec: {models: [], endpoints: []}\n"
    )
    (base / "routes.yaml").write_text(
        "apiVersion: section/v1\nkind: Routes\nspec: []\n"
    )
    (base / "policies" / name).write_text(policy_yaml)


_HEALTHY = """\
apiVersion: section/v1
kind: Policy
metadata: {id: p1, name: p1}
spec:
  match: {routes: ['*']}
  detect:
    enable: [regex, secrets]
  decide:
    rules:
      - when: 'true'
        action: allow
"""


def test_lint_clean_bundle(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, _HEALTHY)
        rc = main(["lint", str(base)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_lint_flags_transform_without_transforms(capsys) -> None:
    bad = """\
apiVersion: section/v1
kind: Policy
metadata: {id: p2, name: p2}
spec:
  match: {routes: ['*']}
  decide:
    rules:
      - when: 'true'
        action: transform
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, bad)
        rc = main(["lint", str(base)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "transforms" in out


def test_lint_flags_duplicate_ids(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, _HEALTHY, name="0001.yaml")
        # Same id again.
        (base / "policies" / "0002.yaml").write_text(_HEALTHY)
        rc = main(["lint", str(base)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "duplicate" in out


def test_lint_warns_on_unknown_detector(capsys) -> None:
    p = """\
apiVersion: section/v1
kind: Policy
metadata: {id: p3, name: p3}
spec:
  match: {routes: ['*']}
  detect:
    enable: [made_up_thing]
  decide:
    rules:
      - when: 'true'
        action: allow
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, p)
        rc = main(["lint", str(base)])
    out = capsys.readouterr().out
    # Warning only, not error.
    assert rc == 0
    assert "made_up_thing" in out
    assert "warning" in out


def test_lint_warns_on_shadowed_allowlist(capsys) -> None:
    p = """\
apiVersion: section/v1
kind: Policy
metadata: {id: p4, name: p4}
spec:
  match: {routes: ['*']}
  decide:
    rules:
      - when: 'true'
        action: allow
  tool_allowlist:
    allow: ['exec_shell']
    deny:  ['exec_*']
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, p)
        rc = main(["lint", str(base)])
    out = capsys.readouterr().out
    assert rc == 0  # warning only
    assert "shadowed" in out


def test_lint_json_output(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, _HEALTHY)
        rc = main(["lint", str(base), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)


def test_test_subcommand_runs_fixtures(capsys) -> None:
    """A fixture expecting action=allow on the healthy bundle passes."""
    fixtures = """\
- name: default-allow
  route: /v1/chat/completions
  tenant_id: tA
  user_id: u1
  findings: []
  expect_action: allow
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, _HEALTHY)
        fx = base / "cases.yaml"
        fx.write_text(fixtures)
        rc = main(["test", str(base), "--fixtures", str(fx)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 passed" in out


def test_test_subcommand_reports_failure(capsys) -> None:
    """Mismatched expectation exits non-zero with a FAIL line."""
    fixtures = """\
- name: should-block
  expect_action: block
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_bundle(base, _HEALTHY)
        fx = base / "cases.yaml"
        fx.write_text(fixtures)
        rc = main(["test", str(base), "--fixtures", str(fx)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


def test_cli_help_runs(capsys) -> None:
    """`section-policy --help` must not crash and must list both subcommands."""
    import pytest

    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "lint" in out
    assert "test" in out
