"""Runtime configuration. All values come from environment (.env file)."""
from __future__ import annotations

import base64
import os
import secrets
import warnings
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pydantic-settings model bound to SECTION_* env vars."""

    model_config = SettingsConfigDict(
        env_file=os.environ.get("SECTION_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    section_env: Literal["development", "staging", "production"] = "development"
    section_log_level: str = "INFO"
    section_host: str = "0.0.0.0"
    section_port: int = 8080
    section_fail_mode: Literal["open", "closed"] = "closed"
    # CORS allowlist for non-development deployments. Comma-separated. In
    # production this should list the exact extension origins
    # (chrome-extension://<id>) plus any browser-origin admin UI.
    section_cors_origins: str = ""

    # --- Auth ---
    section_api_keys: str = "section-demo-key"
    # Comma-separated subset of section_api_keys that are granted the
    # implicit "admin" scope. Empty default means all keys are admin in
    # development (mirrors the prior behaviour where everything was admin-less).
    section_admin_api_keys: str = ""
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    # --- Rate limit ---
    section_rate_limit_rpm: int = 600
    section_rate_limit_enabled: bool = True
    # G4: per-API-key request bucket (RPM). 0 disables the per-key bucket.
    section_rate_limit_per_key_rpm: int = 0
    # G4: per-(tenant, model) token bucket measured in tokens-per-minute,
    # consumed *after* upstream returns based on usage.total_tokens. 0
    # disables the TPM bucket.
    section_rate_limit_tpm_default: int = 0
    # JSON map of {model: tpm} overriding the default per model.
    section_rate_limit_tpm_per_model: str = ""
    # G7: per-tenant detokenise rpm (hardened endpoint).
    section_detok_rate_limit_per_tenant_rpm: int = 30

    # --- SIEM webhook ---
    section_siem_webhook_url: str | None = None
    section_siem_webhook_secret: str | None = None
    section_siem_webhook_timeout_seconds: float = 5.0

    # --- Policy ---
    section_policy_bundle: str = "/etc/section/policies"
    section_policy_reload_seconds: float = 5.0

    # --- Storage ---
    database_url: str = (
        "postgresql+asyncpg://section:section@postgres:5432/section"
    )
    redis_url: str = "redis://redis:6379/0"

    # --- Crypto (base64-32 / hex) ---
    section_vault_key: str = ""
    section_vault_ttl_seconds: int = 3600
    section_fpe_key: str = ""
    section_fpe_tweak: str = ""
    section_audit_signing_key: str | None = None

    # --- Upstream provider creds ---
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    ollama_base_url: str = "http://ollama:11434"

    # --- Observability ---
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "section-gateway"

    # --- Sinks ---
    splunk_hec_url: str | None = None
    splunk_hec_token: str | None = None

    # --- HTTP client tuning ---
    upstream_timeout_seconds: float = 60.0
    upstream_connect_timeout_seconds: float = 10.0
    detector_timeout_seconds: float = 0.08

    # --- Audit writer ---
    audit_batch_size: int = 100
    audit_flush_interval_seconds: float = 1.0
    audit_queue_max: int = 10_000

    @field_validator("section_api_keys")
    @classmethod
    def _strip_keys(cls, v: str) -> str:
        return ",".join(k.strip() for k in v.split(",") if k.strip())

    @property
    def api_key_set(self) -> set[str]:
        return {k for k in self.section_api_keys.split(",") if k}

    @property
    def admin_api_key_set(self) -> set[str]:
        explicit = {k.strip() for k in self.section_admin_api_keys.split(",") if k.strip()}
        # If no explicit list provided, treat every configured key as admin
        # (developer ergonomics). Operators tighten this in prod by setting
        # SECTION_ADMIN_API_KEYS.
        if not explicit:
            return self.api_key_set
        return explicit & self.api_key_set

    @property
    def is_development(self) -> bool:
        return self.section_env == "development"

    @property
    def tpm_per_model_map(self) -> dict[str, int]:
        """Parse the JSON map of model -> TPM overrides.

        Malformed JSON returns an empty map and emits a warning rather than
        crashing the gateway: a typo in an env var shouldn't take production
        down. The default TPM still applies when a model is not listed.
        """
        raw = (self.section_rate_limit_tpm_per_model or "").strip()
        if not raw:
            return {}
        try:
            import json as _json

            parsed = _json.loads(raw)
            if not isinstance(parsed, dict):
                return {}
            return {str(k): int(v) for k, v in parsed.items() if int(v) > 0}
        except (ValueError, TypeError):
            warnings.warn(
                "SECTION_RATE_LIMIT_TPM_PER_MODEL is not valid JSON; ignoring.",
                RuntimeWarning,
                stacklevel=2,
            )
            return {}

    def vault_key_bytes(self) -> bytes:
        """Decode base64 vault key. In dev, auto-generate if absent (with warning)."""
        if not self.section_vault_key or "REPLACE" in self.section_vault_key:
            if self.is_development:
                key = secrets.token_bytes(32)
                warnings.warn(
                    "SECTION_VAULT_KEY not set; generated ephemeral key for "
                    "DEVELOPMENT ONLY. Vault contents will not survive restart.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.section_vault_key = base64.b64encode(key).decode()
                return key
            raise RuntimeError("SECTION_VAULT_KEY required in non-development env")
        raw = base64.b64decode(self.section_vault_key)
        if len(raw) != 32:
            raise RuntimeError("SECTION_VAULT_KEY must decode to exactly 32 bytes")
        return raw

    def fpe_key_bytes(self) -> bytes:
        if not self.section_fpe_key or "REPLACE" in self.section_fpe_key:
            if self.is_development:
                k = secrets.token_bytes(16)
                warnings.warn(
                    "SECTION_FPE_KEY not set; generated ephemeral key for "
                    "DEVELOPMENT ONLY.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.section_fpe_key = k.hex()
                return k
            raise RuntimeError("SECTION_FPE_KEY required in non-development env")
        return bytes.fromhex(self.section_fpe_key)

    def fpe_tweak_bytes(self) -> bytes:
        if not self.section_fpe_tweak or "REPLACE" in self.section_fpe_tweak:
            return b"\x00" * 7  # FF3-1 standard tweak length is 7 bytes
        return bytes.fromhex(self.section_fpe_tweak)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
