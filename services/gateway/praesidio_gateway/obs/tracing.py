"""OpenTelemetry setup. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset."""
from __future__ import annotations

import logging

from ..config import Settings

_log = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> None:
    """Idempotent OTel SDK init. Safe to call once at startup."""
    if not settings.otel_exporter_otlp_endpoint:
        _log.info("OTEL endpoint unset — tracing disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _log.warning("OTel SDK not importable; tracing disabled")
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.praesidio_env,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    _log.info("OTel tracing configured: %s", settings.otel_exporter_otlp_endpoint)


def instrument_fastapi(app) -> None:  # pragma: no cover - optional
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        _log.debug("FastAPI OTel instrumentation skipped", exc_info=True)
