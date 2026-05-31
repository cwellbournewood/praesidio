"""Admin endpoints for inspecting/reloading the policy bundle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...auth import Principal, PrincipalDep, require_admin
from ...policy.loader import PolicyReloadError
from ...state import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/policies")
async def list_policies(
    principal: PrincipalDep, state: AppState = Depends(get_state)
):
    """List loaded policies (id, version, owner, rule count, detector set)."""
    b = state.policy_store.bundle
    return {
        "digest": b.digest,
        "manifest": b.manifest,
        "policies": [
            {
                "id": p.metadata.id,
                "name": p.metadata.name,
                "version": p.metadata.version,
                "owner": p.metadata.owner,
                "fail_mode": p.spec.fail_mode,
                "mode": p.spec.mode,
                "rules": len(p.spec.decide.rules),
                "detectors": p.spec.detect.enable,
            }
            for p in b.policies
        ],
    }


@router.get("/policies/digest")
async def bundle_digest(state: AppState = Depends(get_state)):
    """Return the active bundle's SHA-256 digest (first 64 hex chars)."""
    return {"digest": state.policy_store.bundle.digest}


async def _reload_impl(state: AppState) -> dict:
    """Atomic swap: load (strict) → providers.rebuild → return new digest.

    Failure semantics (G3):

    - A YAML parse error or pydantic validation error returns **422** with
      the per-file ``parse_errors`` list. The previous bundle remains
      active; in-flight requests continue against it without disruption.
    - Any other unexpected exception returns **500**.

    The ``section_policy_reload_total`` counter is incremented inside
    :py:meth:`PolicyStore.reload` (not here) so the watcher and the admin
    endpoint share a single attribution point.
    """
    try:
        bundle = await state.policy_store.reload(strict=True)
    except PolicyReloadError as exc:
        # 422: bundle on disk is invalid; last-good preserved server-side.
        raise HTTPException(
            status_code=422,
            detail={
                "type": "policy_bundle_invalid",
                "message": "bundle reload rejected; previous bundle still active",
                "parse_errors": exc.parse_errors,
            },
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, f"bundle not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(500, f"reload failed: {exc.__class__.__name__}") from exc

    # Provider registry rebuild is best-effort — if a stale models.yaml
    # references an unknown provider we still keep the new bundle live but
    # surface the error. Mostly this is a no-op when models.yaml didn't
    # change.
    try:
        state.providers.rebuild_from_bundle(bundle.models, bundle.routes)
    except Exception as exc:
        raise HTTPException(500, f"provider rebuild failed: {exc.__class__.__name__}") from exc
    return {"reloaded": True, "digest": bundle.digest, "policies": len(bundle.policies)}


@router.post("/policies/reload")
async def reload_bundle(
    principal: Principal = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    """Reload the policy bundle from disk (admin only). Returns new digest."""
    return await _reload_impl(state)


@router.post("/policy/reload")
async def reload_bundle_alias(
    principal: Principal = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    """Alias of ``/admin/policies/reload`` (admin only).

    Provides the singular-noun form requested by external orchestrators.
    Behaviour is identical: atomic swap, ``section_policy_reload_total``
    counter incremented per call.
    """
    return await _reload_impl(state)
