"""GET /admin/models — full model registry view (privileged)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...auth import PrincipalDep
from ...state import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/models")
async def admin_models(principal: PrincipalDep, state: AppState = Depends(get_state)):
    return {
        "models": state.providers.visible_models(),
        "bundle_digest": state.policy_store.bundle.digest,
    }
