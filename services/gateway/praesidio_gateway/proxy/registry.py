"""Provider adapter registry & router.

Resolves the active bundle's ``routes.yaml`` + ``models.yaml`` into a single
function that returns ``(adapter, endpoint_id, model_id)`` for a given
inbound request + decision context.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..policy.dsl import compile_predicate
from ..policy.models import DecisionContext
from .anthropic import AnthropicAdapter
from .azure import AzureOpenAIAdapter
from .base import ProviderAdapter
from .bedrock import BedrockAdapter
from .ollama import OllamaAdapter
from .openai import OpenAIAdapter


@dataclass
class ResolvedRoute:
    model_id: str
    provider: str
    adapter: ProviderAdapter
    endpoint_id: str


class ProviderRegistry:
    """Owns adapter instances and resolves routes against the loaded bundle."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._adapters: dict[str, ProviderAdapter] = {}
        self._models: dict[str, dict[str, Any]] = {}
        self._endpoints: dict[str, dict[str, Any]] = {}
        self._routes: list[dict[str, Any]] = []
        self._blocked: list[dict[str, Any]] = []

    # -- bundle plumbing --------------------------------------------------

    def rebuild_from_bundle(
        self,
        models_doc: dict[str, Any],
        routes_spec: list[dict[str, Any]],
    ) -> None:
        spec = models_doc.get("spec", {}) if isinstance(models_doc, dict) else {}
        self._models = {m["id"]: m for m in spec.get("models", []) if "id" in m}
        self._endpoints = {e["id"]: e for e in spec.get("endpoints", []) if "id" in e}
        self._blocked = list(spec.get("blocked", []))
        self._routes = list(routes_spec or [])

    # -- adapter management ----------------------------------------------

    def _endpoint_base_url(self, ep: dict[str, Any]) -> str:
        if "base_url" in ep:
            url = ep["base_url"]
            # Expand ${ENV_VAR} references
            for k, v in os.environ.items():
                url = url.replace("${" + k + "}", v)
            return url
        if "base_url_env" in ep:
            return os.environ.get(ep["base_url_env"], "") or ""
        return ""

    def _endpoint_api_key(self, ep: dict[str, Any]) -> str | None:
        auth = ep.get("auth") or {}
        if auth.get("type") == "env":
            return os.environ.get(auth.get("var", ""), None)
        return None

    def _adapter_for(self, provider: str, endpoint_id: str) -> ProviderAdapter:
        cache_key = f"{provider}:{endpoint_id}"
        if cache_key in self._adapters:
            return self._adapters[cache_key]
        ep = self._endpoints.get(endpoint_id, {})
        base = self._endpoint_base_url(ep) or self._default_base(provider)
        key = self._endpoint_api_key(ep) or self._default_key(provider)
        if provider == "openai":
            a: ProviderAdapter = OpenAIAdapter(base, key)
        elif provider == "anthropic":
            a = AnthropicAdapter(base, key)
        elif provider == "azure-openai":
            api_version = ep.get("api_version") or self._settings.azure_openai_api_version
            a = AzureOpenAIAdapter(base, key, api_version=api_version)
        elif provider == "ollama":
            a = OllamaAdapter(base or self._settings.ollama_base_url)
        elif provider == "bedrock":
            # Bedrock endpoints carry region + per-model id under endpoint doc.
            region = ep.get("region") or os.environ.get("AWS_REGION", "")
            # The model id on Bedrock is the per-model invoke target; the
            # caller's ``model_id`` (e.g. anthropic.claude-3-...) is forwarded
            # through ``ProviderRegistry.resolve`` and embedded in the URL.
            # When ``model_id`` is not yet known (adapter cache built per
            # endpoint), default to the endpoint's ``default_model``.
            bedrock_model = ep.get("default_model") or ""
            a = BedrockAdapter(region=region, model_id=bedrock_model)
        else:
            raise ValueError(f"unknown provider: {provider}")
        self._adapters[cache_key] = a
        return a

    def _default_base(self, provider: str) -> str:
        s = self._settings
        return {
            "openai": s.openai_base_url,
            "anthropic": s.anthropic_base_url,
            "azure-openai": s.azure_openai_endpoint or "",
            "ollama": s.ollama_base_url,
        }.get(provider, "")

    def _default_key(self, provider: str) -> str | None:
        s = self._settings
        return {
            "openai": s.openai_api_key,
            "anthropic": s.anthropic_api_key,
            "azure-openai": s.azure_openai_api_key,
            "ollama": None,
        }.get(provider)

    # -- public --------------------------------------------------------

    def visible_models(self) -> list[dict[str, Any]]:
        return [{"id": m["id"], **{k: v for k, v in m.items() if k != "id"}} for m in self._models.values()]

    def is_blocked(self, model_id: str) -> bool:
        return any(fnmatch.fnmatchcase(model_id, b.get("pattern", "")) for b in self._blocked)

    def resolve(
        self,
        *,
        inbound_path: str,
        requested_model: str | None,
        ctx: DecisionContext,
        upstream_override: str | None = None,
    ) -> ResolvedRoute:
        """Return a ResolvedRoute. ``upstream_override`` wins if set."""
        env = {
            "principal": ctx.principal.model_dump(),
            "ctx": ctx.model_dump(mode="json"),
            "findings": [],
        }
        chosen_id: str | None = upstream_override
        if not chosen_id:
            for rule in self._routes:
                inbound = rule.get("inbound", {})
                if inbound.get("path") and inbound["path"] != inbound_path:
                    continue
                if inbound.get("requested_model") and requested_model != inbound["requested_model"]:
                    continue
                cond = rule.get("when")
                if cond:
                    try:
                        if not bool(compile_predicate(cond).evaluate(env)):
                            continue
                    except Exception:
                        continue
                chosen_id = rule.get("upstream")
                break
        if not chosen_id:
            # Fall back: passthrough via OpenAI defaults with requested model.
            chosen_id = f"openai/{requested_model or 'gpt-4o-mini'}"

        if self.is_blocked(chosen_id):
            raise PermissionError(f"model {chosen_id} is blocked by policy")

        model_doc = self._models.get(chosen_id, {})
        provider = model_doc.get("provider", chosen_id.split("/", 1)[0])
        endpoint_id = model_doc.get("endpoint_ref", "")
        # `chosen_id` is e.g. "openai/gpt-4o-mini"; rewrite caller's body model.
        model_id = chosen_id.split("/", 1)[1] if "/" in chosen_id else chosen_id
        adapter = self._adapter_for(provider, endpoint_id)
        return ResolvedRoute(model_id=model_id, provider=provider, adapter=adapter, endpoint_id=endpoint_id)

    async def close_all(self) -> None:
        for a in self._adapters.values():
            try:
                await a.close()
            except Exception:  # pragma: no cover
                pass
        self._adapters.clear()
