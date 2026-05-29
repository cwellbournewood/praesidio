"""Health / readiness / metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from ...obs.metrics import render_metrics
from ...state import AppState, get_state

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — always 200 as long as the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(state: AppState = Depends(get_state)):
    """Readiness — DB, Redis, policy bundle all loaded."""
    checks: dict[str, str] = {}
    # DB
    try:
        async with state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"err: {e.__class__.__name__}"
    # Redis (via vault put/get round-trip)
    try:
        await state.vault.put(
            tenant="__readyz__",
            request_id="readyz",
            placeholder="<X_AAAA>",
            plaintext="ping",
            ttl_seconds=5,
        )
        checks["vault"] = "ok"
    except Exception as e:
        checks["vault"] = f"err: {e.__class__.__name__}"
    checks["policy_bundle"] = (
        f"ok (digest={state.policy_store.bundle.digest[:12]})"
        if state.policy_store.loaded()
        else "not_loaded"
    )
    overall_ok = all(v.startswith("ok") for v in checks.values())
    return Response(
        content=str({"status": "ready" if overall_ok else "degraded", **checks}),
        status_code=200 if overall_ok else 503,
        media_type="application/json",
    )


@router.get("/metrics")
async def metrics() -> Response:
    payload, ctype = render_metrics()
    return Response(content=payload, media_type=ctype)
