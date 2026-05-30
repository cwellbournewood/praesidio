"""FastAPI app entry point.

Wires middleware (request id, structured logging), mounts routers, manages
lifespan for the policy store / audit writer / providers.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.admin import detokenise as admin_detokenise
from .api.admin import events as admin_events
from .api.admin import health as admin_health
from .api.admin import labels as admin_labels
from .api.admin import lineage as admin_lineage
from .api.admin import models as admin_models_router
from .api.admin import policies as admin_policies
from .api.admin import simulate as admin_simulate
from .api.anthropic_v1 import messages as anthropic_messages
from .api.azure import chat as azure_chat
from .api.ollama_v1 import chat as ollama_chat
from .api.v1 import chat as v1_chat
from .api.v1 import completions as v1_completions
from .api.v1 import embeddings as v1_embeddings
from .api.v1 import models as v1_models
from .api.v1 import scan as v1_scan
from .config import Settings, get_settings
from .middleware.rate_limit import RateLimitMiddleware
from .obs.logging import configure_logging, log
from .obs.metrics import REQUEST_TOTAL
from .obs.tracing import configure_tracing, instrument_fastapi
from .state import AppState, build_app_state


def _new_request_id() -> str:
    # UUIDv7 isn't in stdlib until 3.12; use uuid4 — sortable-enough for ops.
    return str(uuid.uuid4())


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)
    state: AppState = await build_app_state(settings)
    try:
        await state.policy_store.start(interval=settings.section_policy_reload_seconds)
        state.providers.rebuild_from_bundle(
            state.policy_store.bundle.models, state.policy_store.bundle.routes
        )
        await state.audit.start()
    except Exception:
        log.exception("startup failed")
        raise
    app.state.section = state
    log.info(
        "section gateway ready",
        env=settings.section_env,
        bundle_digest=state.policy_store.bundle.digest[:12],
        policies=len(state.policy_store.bundle.policies),
    )
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await state.audit.stop()
        with contextlib.suppress(Exception):
            await state.policy_store.stop()
        with contextlib.suppress(Exception):
            await state.providers.close_all()
        with contextlib.suppress(Exception):
            await state.vault.close()
        with contextlib.suppress(Exception):
            await state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Section Gateway",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/admin/docs",
        openapi_url="/admin/openapi.json",
    )

    # ---- middlewares ----
    @app.middleware("http")
    async def _request_id_mw(request: Request, call_next):
        rid = request.headers.get("x-request-id") or _new_request_id()
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error")
            REQUEST_TOTAL.labels(
                route=request.url.path, method=request.method, status="500"
            ).inc()
            return JSONResponse(
                {"error": {"type": "internal", "message": "internal error"}},
                status_code=500,
                headers={"x-request-id": rid},
            )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["x-request-id"] = rid
        response.headers["x-section-latency-ms"] = str(elapsed_ms)
        REQUEST_TOTAL.labels(
            route=request.url.path, method=request.method, status=str(response.status_code)
        ).inc()
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        structlog.contextvars.unbind_contextvars("request_id")
        return response

    # CORS — the 1.1 browser extension's service worker hits /v1/scan +
    # /v1/restore from a chrome-extension:// origin. host_permissions in
    # the manifest grants the extension cross-origin fetch directly, but
    # for development against `make gateway` from a regular browser tab
    # we also need server-side CORS. Allowed origins are configurable;
    # defaults cover localhost dev + any chrome-extension origin.
    settings = get_settings()
    if settings.section_env == "development":
        # In dev, accept any chrome-extension:// origin so unpacked-loaded
        # extensions (which have random IDs) work without manual whitelisting.
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"^(chrome-extension://[a-z]{32}|moz-extension://[a-z0-9-]+|http://localhost:\d+|http://127\.0\.0\.1:\d+)$",
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=[
                "X-Section-Decision",
                "X-Section-Reason",
                "X-Section-Severity",
                "X-Section-Request-Id",
                "X-Section-Policy",
                "X-Request-Id",
            ],
        )
    else:
        # In production, operators MUST set SECTION_CORS_ORIGINS to the
        # exact extension ID(s) they distribute.
        configured = [o.strip() for o in (settings.section_cors_origins or "").split(",") if o.strip()]
        if configured:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=configured,
                allow_credentials=False,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
            )

    # Per-tenant Redis token-bucket rate limit. Excludes /healthz and /metrics.
    if settings.section_rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            rpm=settings.section_rate_limit_rpm,
            redis_url=settings.redis_url,
            per_key_rpm=settings.section_rate_limit_per_key_rpm,
            tpm_default=settings.section_rate_limit_tpm_default,
            tpm_per_model=settings.tpm_per_model_map,
        )

    # ---- routers ----
    app.include_router(v1_chat.router)
    app.include_router(v1_completions.router)
    app.include_router(v1_embeddings.router)
    app.include_router(v1_models.router)
    app.include_router(v1_scan.router)
    app.include_router(anthropic_messages.router)
    app.include_router(azure_chat.router)
    app.include_router(ollama_chat.router)
    app.include_router(admin_health.router)
    app.include_router(admin_events.router)
    app.include_router(admin_policies.router)
    app.include_router(admin_lineage.router)
    app.include_router(admin_models_router.router)
    app.include_router(admin_simulate.router)
    app.include_router(admin_detokenise.router)
    app.include_router(admin_labels.router)

    # --- vectors lane V ---
    # Mount the vector-store router so operators get DLP-on-write and
    # ACL-on-read endpoints out of the box. The router has zero side
    # effects until a concrete connector is registered — operators wire
    # those in their deployment overlay (Helm hook / Compose init / a
    # custom on_startup) by calling::
    #
    #   from section_gateway.api.vectors import register_connector
    #   from section_gateway.vectors.pgvector import PgVectorConnector
    #   register_connector("pgvector", PgVectorConnector(...))
    #
    # Keeping the wiring out of create_app() avoids coupling startup to
    # optional dependencies (asyncpg, qdrant-client) and lets tests
    # import this module without booting a backend.
    from .api import vectors as vectors_router  # noqa: PLC0415

    app.include_router(vectors_router.router)
    # --- end vectors lane V ---

    instrument_fastapi(app)
    return app


app = create_app()


def _print_config(settings: Settings) -> None:
    redacted = settings.model_dump()
    for k in list(redacted):
        if any(s in k for s in ("key", "secret", "password", "token")):
            redacted[k] = "***" if redacted[k] else ""
    for k, v in redacted.items():
        print(f"{k}={v}")


def run() -> None:
    parser = argparse.ArgumentParser("section-gateway")
    parser.add_argument("--print-config", action="store_true")
    args, _ = parser.parse_known_args()

    settings = get_settings()
    if args.print_config:
        _print_config(settings)
        return

    import uvicorn

    uvicorn.run(
        "section_gateway.main:app",
        host=settings.section_host,
        port=settings.section_port,
        log_level=settings.section_log_level.lower(),
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    sys.exit(run() or 0)
