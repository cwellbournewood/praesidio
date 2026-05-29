"""GET /v1/models — visible-models filter from the policy bundle's registry."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from ...auth import PrincipalDep
from ...state import AppState, get_state

router = APIRouter(tags=["openai"])


@router.get("/v1/models")
async def list_models(
    principal: PrincipalDep,
    state: AppState = Depends(get_state),
):
    models = state.providers.visible_models()
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": m.get("provider", "praesidio"),
                "praesidio": {
                    "jurisdiction": m.get("jurisdiction"),
                    "risk_tier": m.get("risk_tier"),
                    "privacy": m.get("privacy"),
                },
            }
            for m in models
        ],
    }
