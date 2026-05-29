"""Upstream allowlist and routing helpers.

Maps an inbound HTTPS host+path to a provider id plus an extractor key.
Anything not in :data:`UPSTREAMS` is passed through unmodified — we only
intercept LLM provider hosts that we know how to parse.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import extractors


@dataclass(frozen=True)
class Upstream:
    """Description of a provider hostname we know how to scan.

    Attributes:
        provider: Short name used in audit tags (``"openai"``, ``"anthropic"``, ...).
        host: Lowercase hostname matched against ``request.host``.
        extractor: Callable that walks the JSON body to pull/replace prompt text.
        model_field: Optional dotted key into the request JSON that holds
            the model id; we send it to ``/v1/scan`` as the ``model`` hint.
        path_patterns: List of URL-path substrings; we only intercept if
            the request path contains one of these (avoids scanning
            account / billing / status endpoints by accident). Empty
            means "intercept all paths on this host".
    """

    provider: str
    host: str
    extractor: extractors.Extractor
    model_field: str | None
    path_patterns: tuple[str, ...]


UPSTREAMS: tuple[Upstream, ...] = (
    Upstream(
        provider="openai",
        host="api.openai.com",
        extractor=extractors.openai_chat,
        model_field="model",
        path_patterns=("/v1/chat/completions", "/v1/completions", "/v1/responses"),
    ),
    Upstream(
        provider="anthropic",
        host="api.anthropic.com",
        extractor=extractors.anthropic_messages,
        model_field="model",
        path_patterns=("/v1/messages",),
    ),
    Upstream(
        provider="gemini",
        host="generativelanguage.googleapis.com",
        extractor=extractors.gemini_generate,
        # Gemini puts the model in the URL path, not the body.
        model_field=None,
        path_patterns=(":generateContent", ":streamGenerateContent"),
    ),
    Upstream(
        provider="cohere",
        host="api.cohere.ai",
        extractor=extractors.cohere_chat,
        model_field="model",
        path_patterns=("/v1/chat", "/v2/chat", "/v1/generate"),
    ),
    Upstream(
        provider="mistral",
        host="api.mistral.ai",
        extractor=extractors.openai_chat,  # OpenAI-shape API
        model_field="model",
        path_patterns=("/v1/chat/completions", "/v1/fim/completions"),
    ),
    Upstream(
        provider="perplexity",
        host="api.perplexity.ai",
        extractor=extractors.openai_chat,
        model_field="model",
        path_patterns=("/chat/completions",),
    ),
    Upstream(
        provider="groq",
        host="api.groq.com",
        extractor=extractors.openai_chat,
        model_field="model",
        path_patterns=("/openai/v1/chat/completions",),
    ),
    Upstream(
        provider="deepseek",
        host="api.deepseek.com",
        extractor=extractors.openai_chat,
        model_field="model",
        path_patterns=("/v1/chat/completions", "/chat/completions"),
    ),
)

_BY_HOST: dict[str, Upstream] = {u.host: u for u in UPSTREAMS}


def lookup(host: str, path: str) -> Upstream | None:
    """Return the :class:`Upstream` entry that matches *host* + *path*.

    Args:
        host: Inbound request hostname (no port). Case-insensitive.
        path: Inbound request path (may include query string).

    Returns:
        Matching :class:`Upstream` or ``None`` if the host is not in the
        allowlist or if its path patterns don't match.
    """
    if not host:
        return None
    u = _BY_HOST.get(host.lower())
    if u is None:
        return None
    if not u.path_patterns:
        return u
    for pat in u.path_patterns:
        if pat in path:
            return u
    return None


def intercepted_hosts() -> list[str]:
    """List every host we intercept, in declaration order."""
    return [u.host for u in UPSTREAMS]
