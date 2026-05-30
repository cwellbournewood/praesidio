"""Runtime configuration for the Section edge proxy.

Loaded from environment variables (``SECTION_EDGE_*``) and CLI flags.
CLI flags win over env vars. Anything sensitive (the API key) should
come from the OS keychain — we never log or persist it.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EdgeSettings(BaseSettings):
    """Edge-proxy runtime settings.

    Environment-variable prefix: ``SECTION_EDGE_``. All fields can be
    overridden by CLI flags via :func:`section_edge_proxy.cli.build_settings`.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECTION_EDGE_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    gateway_url: str = Field(
        default="http://127.0.0.1:8080",
        description="Section gateway base URL (no trailing /v1).",
    )
    api_key: str = Field(
        default="",
        description="API key presented as `X-API-Key` to the gateway.",
    )
    tenant: str = Field(
        default="default",
        description="Tenant id presented as `X-Section-Tenant`.",
    )
    listen_host: str = Field(default="127.0.0.1")
    listen_port: int = Field(default=8888, ge=1, le=65535)

    # CA / install paths — see :mod:`section_edge_proxy.ca` for defaults.
    ca_dir: Path | None = Field(
        default=None,
        description=(
            "Override directory for CA cert + key. Defaults to a per-OS "
            "application data dir (LOCALAPPDATA / ~/Library/Application Support / "
            "$XDG_DATA_HOME)."
        ),
    )

    # Operational knobs.
    request_timeout_s: float = Field(default=8.0, gt=0.0)
    restore_timeout_s: float = Field(default=8.0, gt=0.0)
    session_id_header: str = Field(
        default="x-section-session-id",
        description="Header the upstream client may set to thread vault scope across calls.",
    )
    fail_open: bool = Field(
        default=False,
        description=(
            "If true, gateway errors let the request through unchanged "
            "(unsafe — used only for development)."
        ),
    )
    log_level: str = Field(default="INFO")

    @field_validator("gateway_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def scan_url(self) -> str:
        return f"{self.gateway_url}/v1/scan"

    @property
    def restore_url(self) -> str:
        return f"{self.gateway_url}/v1/restore"
