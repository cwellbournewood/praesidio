"""Process-wide composition root, accessed via FastAPI dependency injection."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .anonymize.vault import TokenVault, build_vault
from .audit.models import Base
from .audit.sinks.splunk_hec import SplunkHECSink
from .audit.sinks.webhook import SiemWebhookSink
from .audit.writer import AuditWriter
from .config import Settings, get_settings
from .policy.loader import PolicyStore
from .proxy.registry import ProviderRegistry


@dataclass
class AppState:
    settings: Settings
    policy_store: PolicyStore
    vault: TokenVault
    engine: AsyncEngine
    audit: AuditWriter
    providers: ProviderRegistry


async def build_app_state(settings: Settings | None = None) -> AppState:
    settings = settings or get_settings()
    vault = build_vault(settings.vault_key_bytes(), settings.redis_url)
    # SQLAlchemy options vary by driver — sqlite+aiosqlite (used in tests) does
    # not accept `pool_pre_ping` on the underlying connection pool the same way.
    engine_kwargs: dict = {"future": True}
    if not settings.database_url.startswith("sqlite"):
        engine_kwargs["pool_pre_ping"] = True
    engine = create_async_engine(settings.database_url, **engine_kwargs)
    # Auto-create tables for SQLite (tests / local dev without migrations).
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    splunk = SplunkHECSink(settings.splunk_hec_url, settings.splunk_hec_token)
    webhook = SiemWebhookSink(
        settings.section_siem_webhook_url,
        settings.section_siem_webhook_secret,
        timeout=settings.section_siem_webhook_timeout_seconds,
    )
    writer = AuditWriter(
        engine,
        batch_size=settings.audit_batch_size,
        flush_interval=settings.audit_flush_interval_seconds,
        queue_max=settings.audit_queue_max,
        splunk=splunk,
        webhook=webhook,
    )
    store = PolicyStore(settings.section_policy_bundle)
    providers = ProviderRegistry(settings)
    return AppState(
        settings=settings,
        policy_store=store,
        vault=vault,
        engine=engine,
        audit=writer,
        providers=providers,
    )


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "section", None)
    if state is None:
        raise RuntimeError("AppState not initialised")
    return state


StateDep = Depends(get_state)
