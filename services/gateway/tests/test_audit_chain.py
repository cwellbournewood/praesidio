"""Hash-chain continuity tests."""
from __future__ import annotations

from praesidio_gateway.audit.chain import compute_chain_hash, verify_chain


def _row(i: int, tenant: str = "t1") -> dict:
    return {
        "id": f"00000000-0000-0000-0000-00000000000{i}",
        "tenant_id": tenant,
        "decision": "allow",
        "occurred_at": "2026-05-27T00:00:00+00:00",
        "policy_id": "p",
        "findings": [{"label": "x"}],
    }


def test_chain_continuity_across_three_events():
    rows = []
    prev = None
    for i in range(3):
        r = _row(i)
        r["prev_hash"] = prev
        r["chain_hash"] = compute_chain_hash(prev, r)
        rows.append(r)
        prev = r["chain_hash"]
    ok, bad = verify_chain(rows)
    assert ok and bad is None


def test_mutation_breaks_chain():
    rows = []
    prev = None
    for i in range(3):
        r = _row(i)
        r["prev_hash"] = prev
        r["chain_hash"] = compute_chain_hash(prev, r)
        rows.append(r)
        prev = r["chain_hash"]
    # Mutate the middle row's payload — chain on the middle row should now fail.
    rows[1]["decision"] = "block"
    ok, bad = verify_chain(rows)
    assert not ok
    assert bad == 1


def test_different_tenants_independent():
    """Two tenants sharing the same writer should have independent chains."""
    # In this unit test we just confirm compute_chain_hash treats prev_hash as
    # the chain seed; the writer enforces tenant scoping when reading it.
    a = compute_chain_hash(None, _row(0, "tenant-a"))
    b = compute_chain_hash(None, _row(0, "tenant-b"))
    assert a != b
