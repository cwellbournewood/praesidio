"""Praesidio Edge Proxy — local CA MITM for LLM-API traffic.

This package boots a mitmproxy-based local HTTPS proxy that:

* Generates a per-machine root CA on first run and installs it into the
  OS trust store (Windows / macOS / Linux).
* Intercepts a fixed allowlist of LLM provider hostnames
  (``api.openai.com``, ``api.anthropic.com``, ``generativelanguage.googleapis.com``,
  ``api.cohere.ai``, ``api.mistral.ai``, ``api.perplexity.ai``, ``api.groq.com``,
  ``api.deepseek.com``).
* For each intercepted request, extracts the prompt text from the
  provider-specific JSON shape and POSTs it to the Praesidio gateway's
  ``/v1/scan`` endpoint.
* On ``action="block"`` returns HTTP 403 to the caller with the gateway's
  standard ``praesidio_blocked`` error body.
* On ``action="mask"`` rewrites the request body with the sanitised text
  and forwards to the real upstream, then runs the response body
  through ``/v1/restore`` so placeholders are swapped back in before the
  caller sees the reply. Streaming (SSE) responses are processed event
  by event with a placeholder cache that survives chunk boundaries.
* On ``action="allow"`` forwards unchanged.

The proxy is intended for endpoint coverage of tools that respect
``HTTPS_PROXY``: Cursor, Claude Code, Continue, aider, Cline, Copilot
CLI, Zed AI, and any other CLI/IDE that resolves LLM providers through
the system proxy.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
