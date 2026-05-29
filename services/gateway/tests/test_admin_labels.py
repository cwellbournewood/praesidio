"""Tests for ``GET /admin/labels`` — the operator-facing display catalogue.

Three things matter:

1. The endpoint returns one entry per registered label, with the wire id
   in the canonical ``<category>.<thing>`` shape.
2. Every entry carries a non-empty ``name`` and ``description`` (the
   whole point is being human-readable).
3. The response is cacheable: a stable ETag is set and the body is
   identical on consecutive calls (process-static).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from praesidio_gateway.dlp.display import LABELS, categories
from praesidio_gateway.main import create_app

_LABEL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_admin_labels_returns_full_catalogue(client: TestClient) -> None:
    r = client.get("/admin/labels")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1"
    assert body["count"] == len(LABELS)
    assert body["categories"] == categories()
    assert len(body["labels"]) == len(LABELS)


def test_admin_labels_every_entry_is_human_readable(client: TestClient) -> None:
    body = client.get("/admin/labels").json()
    for entry in body["labels"]:
        assert _LABEL_ID_RE.match(entry["id"]), entry["id"]
        assert entry["category"] in categories()
        assert entry["severity"] in {"low", "medium", "high", "critical"}
        assert entry["name"], f"empty name for {entry['id']}"
        assert entry["description"], f"empty description for {entry['id']}"
        # short is the placeholder fragment — uppercase letters, digits, underscore
        assert re.match(r"^[A-Z][A-Z0-9_]*$", entry["short"]), entry["short"]


def test_admin_labels_is_cacheable(client: TestClient) -> None:
    r1 = client.get("/admin/labels")
    r2 = client.get("/admin/labels")
    assert r1.headers["etag"] == r2.headers["etag"]
    assert "max-age" in r1.headers.get("cache-control", "")
    # Bodies are byte-stable so an intermediate cache layer can dedupe.
    assert r1.content == r2.content


def test_admin_labels_includes_known_renamed_entries(client: TestClient) -> None:
    """Sanity-check the rename actually shipped — these specific entries
    are the ones the user called out as opaque (``presidio.ORG`` etc)."""
    by_id = {e["id"]: e for e in client.get("/admin/labels").json()["labels"]}
    org = by_id["pii.organization"]
    assert org["name"] == "Organization name"
    assert org["short"] == "ORGANIZATION"
    cc = by_id["financial.credit_card"]
    assert cc["short"] == "CREDIT_CARD"
    nrp = by_id["pii.nationality"]
    assert nrp["short"] == "NATIONALITY"
