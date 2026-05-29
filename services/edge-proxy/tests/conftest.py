"""Shared fixtures for the edge-proxy test suite.

Two big ideas:

* We don't boot the real mitmproxy network stack. The :class:`PraesidioAddon`
  hooks (``request``/``response``) accept any object that quacks like a
  ``mitmproxy.http.HTTPFlow`` — we build a minimal fake in
  :class:`FakeFlow` and exercise the hooks directly. This is the same
  trick mitmproxy's own ``itest`` helpers use under the hood and matches
  the "minimal HTTP fixture" path called out in the spec.
* The gateway is mocked with ``respx``. Every test that wants to
  observe a /v1/scan or /v1/restore call routes through :func:`gateway_mock`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from praesidio_edge_proxy.config import EdgeSettings


@pytest.fixture
def tmp_ca_dir(tmp_path: Path) -> Path:
    """Per-test CA dir. Keeps trust-store + key material out of the user's home."""
    return tmp_path / "praesidio"


@pytest.fixture
def settings(tmp_ca_dir: Path) -> EdgeSettings:
    return EdgeSettings(
        gateway_url="http://gateway.test",
        api_key="test-key",
        tenant="default",
        ca_dir=tmp_ca_dir,
    )


@pytest.fixture
def gateway_mock() -> respx.MockRouter:
    """respx mock for the gateway's `/v1/scan` and `/v1/restore`.

    Yields a configured :class:`respx.MockRouter`. Default routes
    return an `allow` decision for `/v1/scan` and a no-op for
    `/v1/restore`; individual tests override per call.
    """
    with respx.mock(assert_all_called=False) as router:
        router.post("http://gateway.test/v1/scan").respond(
            200,
            json={
                "request_id": "req-allow",
                "action": "allow",
                "sanitised": None,
                "transforms": [],
                "findings": [],
                "decision": {},
                "bundle_digest": "abc",
            },
        )
        router.post("http://gateway.test/v1/restore").respond(
            200,
            json={
                "request_id": "req-allow",
                "text": "",
                "restored": 0,
                "missing": [],
            },
        )
        yield router


# ---------------------------------------------------------------------------
# Minimal mitmproxy-compatible fakes — enough to drive the request and
# response hooks without booting the proxy.
# ---------------------------------------------------------------------------


class FakeHeaders(dict):
    """Case-insensitive header dict (mitmproxy's Headers is similar)."""

    def __init__(self, items: dict[str, str] | None = None):
        super().__init__()
        for k, v in (items or {}).items():
            self[k.lower()] = v

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return super().get(key.lower(), default)

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)


class FakeRequest:
    """Stand-in for ``mitmproxy.http.Request``."""

    def __init__(
        self,
        *,
        host: str,
        path: str,
        method: str = "POST",
        body: bytes | str = b"",
        headers: dict[str, str] | None = None,
    ):
        self.host = host
        self.pretty_host = host
        self.path = path
        self.method = method
        if isinstance(body, str):
            self.content = body.encode("utf-8")
        else:
            self.content = body
        self.headers = FakeHeaders(headers or {})

    def get_text(self) -> str:
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def set_text(self, text: str) -> None:
        self.content = text.encode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class FakeResponse:
    """Stand-in for ``mitmproxy.http.Response``."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes | str = b"",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        if isinstance(body, str):
            self.content = body.encode("utf-8")
        else:
            self.content = body
        self.headers = FakeHeaders(headers or {})

    def get_text(self) -> str:
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def set_text(self, text: str) -> None:
        self.content = text.encode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class FakeFlow:
    """Stand-in for ``mitmproxy.http.HTTPFlow``."""

    def __init__(self, request: FakeRequest, response: FakeResponse | None = None):
        self.request = request
        self.response = response
        self.metadata: dict[str, Any] = {}


@pytest.fixture
def fake_flow_factory() -> Any:
    """Factory for building :class:`FakeFlow` objects in tests."""

    def _make(
        *,
        host: str,
        path: str,
        body: dict[str, Any] | str | bytes | None = None,
        headers: dict[str, str] | None = None,
        response: FakeResponse | None = None,
    ) -> FakeFlow:
        if isinstance(body, dict):
            body_bytes = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")
        elif isinstance(body, bytes):
            body_bytes = body
        else:
            body_bytes = b""
        req = FakeRequest(host=host, path=path, body=body_bytes, headers=headers)
        return FakeFlow(req, response)

    return _make


@pytest.fixture
def gateway_client(settings: EdgeSettings) -> Any:
    """A real :class:`GatewayClient` wired up to httpx + respx (no real network)."""
    from praesidio_edge_proxy.scan_client import GatewayClient

    return GatewayClient(
        settings,
        client=httpx.AsyncClient(timeout=httpx.Timeout(2.0), verify=False),
    )
