"""Hash-chain provenance.

`chain_hash = sha256( prev_hash || canonical_json(row_without_chain_hash) )`

`prev_hash` is the previous row's chain hash *for the same tenant*. The
audit writer loads it atomically inside the same DB transaction that inserts
the new row so concurrent writers can't race.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

# Fields excluded from the canonical row used to compute chain_hash.
_EXCLUDE = {"chain_hash", "signature"}


def canonical_row_bytes(row: dict[str, Any]) -> bytes:
    """Stable canonical-JSON byte form of a row (sorted keys, no whitespace)."""
    clean = {k: row[k] for k in sorted(row) if k not in _EXCLUDE}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), default=_jsonable).encode(
        "utf-8"
    )


def _jsonable(o: Any) -> Any:
    # datetimes -> ISO (always UTC-aware so naive round-trips from SQLite
    # hash the same as the tz-aware value the writer originally stored).
    if isinstance(o, datetime):
        if o.tzinfo is None:
            o = o.replace(tzinfo=UTC)
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (bytes, bytearray)):
        return o.hex()
    if isinstance(o, (set, tuple, frozenset)):
        return list(o)
    raise TypeError(f"unserialisable type: {type(o).__name__}")


def compute_chain_hash(prev_hash: str | None, row: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update((prev_hash or "").encode("ascii"))
    h.update(b"|")
    h.update(canonical_row_bytes(row))
    return h.hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Verify a list of rows (ordered by occurred_at asc).

    Returns ``(ok, first_bad_index)``.
    """
    prev = None
    for i, row in enumerate(rows):
        expected = compute_chain_hash(prev, {k: v for k, v in row.items() if k != "chain_hash"})
        if row.get("chain_hash") != expected:
            return False, i
        prev = row["chain_hash"]
    return True, None
