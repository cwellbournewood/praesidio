"""Identity resolution. Produces a Principal for each request."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings, get_settings


def api_key_fingerprint(api_key: str) -> str:
    """Return the 8-hex-char prefix of sha256(api_key).

    Used as a stable, non-reversible identifier for an API key. The raw key
    is never logged or persisted; only this fingerprint.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True, slots=True)
class Principal:
    """Resolved caller identity. Becomes part of every DecisionContext."""

    user_id: str
    tenant_id: str
    groups: tuple[str, ...] = ()
    country: str | None = None
    device_id: str | None = None
    source_ip: str | None = None
    auth_method: str = "api_key"
    scopes: tuple[str, ...] = ()
    raw_claims: dict = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes

    def is_admin(self) -> bool:
        return "admin" in self.scopes or "admin" in self.groups


def _parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def resolve_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_tenant: Annotated[str | None, Header(alias="X-Section-Tenant")] = None,
    x_user: Annotated[str | None, Header(alias="X-Section-User")] = None,
    x_groups: Annotated[str | None, Header(alias="X-Section-Groups")] = None,
    x_country: Annotated[str | None, Header(alias="X-Section-Country")] = None,
    x_scopes: Annotated[str | None, Header(alias="X-Section-Scopes")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve a Principal from headers.

    Accepts ``X-API-Key`` or an ``Authorization: Bearer …`` header. The OIDC
    branch is intentionally deferred to a verified-JWT helper plugged in by
    the operator; the gateway accepts ``X-Section-*`` headers from a
    trusted upstream (e.g. an auth proxy) by default.
    """
    api_key = x_api_key or _parse_bearer(authorization)
    if not api_key or api_key not in settings.api_key_set:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid api key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_id = (x_tenant or "default").strip()
    fp = api_key_fingerprint(api_key)
    user_id = (x_user or f"apikey:{fp}").strip()
    groups = tuple(g.strip() for g in (x_groups or "").split(",") if g.strip())
    scopes = tuple(s.strip() for s in (x_scopes or "").split(",") if s.strip())
    # Default-grant: keys configured as admin in SECTION_ADMIN_API_KEYS get
    # the implicit "admin" scope (which also satisfies any specific scope check).
    if api_key in settings.admin_api_key_set:
        scopes = tuple({*scopes, "admin"})
    src_ip = (
        request.client.host
        if request.client is not None
        else request.headers.get("x-forwarded-for", "").split(",")[0].strip() or None
    )

    return Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        groups=groups,
        country=x_country,
        source_ip=src_ip,
        auth_method="api_key",
        scopes=scopes,
        raw_claims={"api_key_fp": fp},
    )


PrincipalDep = Annotated[Principal, Depends(resolve_principal)]


def require_scope(scope: str):
    """FastAPI dependency that 403s when the principal lacks ``scope``."""

    def _dep(principal: PrincipalDep) -> Principal:
        if not principal.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing required scope: {scope}",
            )
        return principal

    return _dep


def require_admin(principal: PrincipalDep) -> Principal:
    """FastAPI dependency that 403s when the principal isn't an admin."""
    if not principal.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin scope required",
        )
    return principal
