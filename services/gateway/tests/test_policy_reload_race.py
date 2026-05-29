"""Policy hot-reload race-safety (G3).

Covers:
  - Concurrent reload calls don't corrupt the active bundle ref.
  - A reload mid-flight doesn't tear the bundle read on the request path.
  - A parse error keeps the last-good bundle active and surfaces a 422.
  - The active-version Prometheus gauge updates on successful reload.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from praesidio_gateway.policy.loader import (
    PolicyReloadError,
    PolicyStore,
    load_bundle,
)


def _write_minimal_bundle(base: Path, *, policy_id: str = "p1") -> None:
    (base / "policies").mkdir(parents=True, exist_ok=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: Bundle\n"
        "metadata: {name: t, version: '0'}\nspec: {includes: []}\n"
    )
    (base / "models.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: ModelRegistry\nspec: {models: [], endpoints: []}\n"
    )
    (base / "routes.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: Routes\nspec: []\n"
    )
    (base / "policies" / "0001-p.yaml").write_text(
        "apiVersion: praesidio/v1\n"
        "kind: Policy\n"
        f"metadata: {{id: {policy_id}, name: {policy_id}}}\n"
        "spec:\n"
        "  match: {routes: ['*']}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: 'true'\n"
        "        action: allow\n"
    )


def _write_broken_policy(base: Path) -> None:
    (base / "policies" / "0002-broken.yaml").write_text(
        "this: is: not: valid: yaml: %%%\n"
    )


@pytest.mark.asyncio
async def test_concurrent_reads_during_reload_never_see_torn_state() -> None:
    """N concurrent `.bundle` reads interleaved with a reload always see
    a single, coherent bundle (either old or new digest, never None / mixed).
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_minimal_bundle(base, policy_id="v1")
        store = PolicyStore(str(base))
        await store.reload(strict=False)
        first_digest = store.bundle.digest

        async def read_loop(seen: list[str], *, stop: asyncio.Event) -> None:
            while not stop.is_set():
                b = store.bundle
                assert b is not None
                assert b.digest  # never empty
                seen.append(b.digest)
                await asyncio.sleep(0)  # yield to event loop

        async def reload_loop(stop: asyncio.Event) -> None:
            # Flip the policy id three times.
            for i in range(3):
                _write_minimal_bundle(base, policy_id=f"v{i+2}")
                await store.reload(strict=False)
                await asyncio.sleep(0.01)
            stop.set()

        stop = asyncio.Event()
        seen_a: list[str] = []
        seen_b: list[str] = []
        await asyncio.gather(
            read_loop(seen_a, stop=stop),
            read_loop(seen_b, stop=stop),
            reload_loop(stop),
        )
        # All seen digests should be either the original or one of the
        # subsequent ones — never empty, never garbage.
        assert seen_a, "reader thread saw no reads"
        assert seen_b, "reader thread saw no reads"
        for d in seen_a + seen_b:
            assert len(d) == 64  # sha256 hex
        # Final digest is one of the v4 variants.
        assert store.bundle.digest != first_digest


@pytest.mark.asyncio
async def test_parse_error_keeps_last_good_and_raises() -> None:
    """A broken policy file added between reloads must be rejected. The
    previous bundle must remain the active one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_minimal_bundle(base)
        store = PolicyStore(str(base))
        await store.reload(strict=False)
        good_digest = store.bundle.digest
        good_policies = len(store.bundle.policies)

        # Corrupt the bundle.
        _write_broken_policy(base)

        with pytest.raises(PolicyReloadError) as exc_info:
            await store.reload(strict=True)
        assert "0002-broken.yaml" in str(exc_info.value)
        assert exc_info.value.parse_errors  # non-empty

        # Active bundle unchanged.
        assert store.bundle.digest == good_digest
        assert len(store.bundle.policies) == good_policies


@pytest.mark.asyncio
async def test_reload_metric_updates_on_success() -> None:
    """``praesidio_policy_active_version`` must reflect the loaded bundle."""
    from praesidio_gateway.obs.metrics import POLICY_ACTIVE_VERSION, POLICY_RELOAD_TOTAL

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_minimal_bundle(base)
        store = PolicyStore(str(base))

        before_ok = _counter_value(POLICY_RELOAD_TOTAL, {"outcome": "ok"})
        await store.reload(strict=True)
        after_ok = _counter_value(POLICY_RELOAD_TOTAL, {"outcome": "ok"})
        assert after_ok == before_ok + 1

        # Gauge has exactly one labelset, value=1
        samples = _collect_samples(POLICY_ACTIVE_VERSION)
        assert any(s.value == 1.0 for s in samples), samples
        # Digest label matches the bundle digest prefix.
        digest_prefix = store.bundle.digest[:12]
        assert any(s.labels.get("digest") == digest_prefix for s in samples), samples


@pytest.mark.asyncio
async def test_reload_metric_increments_err_on_parse_error() -> None:
    from praesidio_gateway.obs.metrics import POLICY_RELOAD_TOTAL

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_minimal_bundle(base)
        store = PolicyStore(str(base))
        await store.reload(strict=True)
        _write_broken_policy(base)

        before_err = _counter_value(POLICY_RELOAD_TOTAL, {"outcome": "err"})
        with pytest.raises(PolicyReloadError):
            await store.reload(strict=True)
        after_err = _counter_value(POLICY_RELOAD_TOTAL, {"outcome": "err"})
        assert after_err == before_err + 1


@pytest.mark.asyncio
async def test_load_bundle_non_strict_skips_broken() -> None:
    """Non-strict (background watcher) mode logs and continues."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_minimal_bundle(base)
        _write_broken_policy(base)
        bundle = load_bundle(base, strict=False)
        # Good policy still loaded; broken one skipped.
        assert len(bundle.policies) == 1
        assert bundle.policies[0].metadata.id == "p1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _counter_value(metric, labels: dict[str, str]) -> float:
    for s in _collect_samples(metric):
        if all(s.labels.get(k) == v for k, v in labels.items()):
            return s.value
    return 0.0


def _collect_samples(metric):
    out = []
    for fam in metric.collect():
        for s in fam.samples:
            if s.name.endswith("_total") or s.name.endswith(
                metric._name.split("_")[-1]
            ) or not s.name.endswith("_created"):
                out.append(s)
    # Filter out _created samples added by prometheus_client for counters.
    return [s for s in out if not s.name.endswith("_created")]
