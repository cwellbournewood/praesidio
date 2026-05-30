"""Pydantic models for the policy DSL and decision objects."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Findings (mirrors dlp.detectors output but lives here to avoid cycles)
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """Detector output. Raw matched text is NEVER stored — only its sha256."""

    model_config = ConfigDict(frozen=False, extra="forbid")

    id: str
    label: str
    start: int
    end: int
    text_hash: str = Field(..., min_length=64, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    detector: str
    detector_version: str = "0"
    meta: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

TransformMethod = Literal["tokenise", "fpe", "redact"]
TransformScope = Literal["request", "session", "tenant"]


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str  # e.g. "pii.email" or "*"
    method: TransformMethod
    scope: TransformScope = "request"
    ttl: str | None = None  # "1h", "30m", "24h"
    replacement: str | None = None  # for redact


# ---------------------------------------------------------------------------
# Policy YAML
# ---------------------------------------------------------------------------


class MatchSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    routes: list[str] = Field(default_factory=lambda: ["*"])
    tenants: list[str] = Field(default_factory=lambda: ["*"])
    principals: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=lambda: ["*"])


class DetectSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    enable: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    when: str
    action: Literal["allow", "transform", "block"]
    transforms: list[Transform] = Field(default_factory=list)
    reason: str | None = None
    severity: str | None = None


class RouteOverride(BaseModel):
    model_config = ConfigDict(extra="allow")
    when_jurisdiction: str | None = None
    upstream: str | None = None
    when: str | None = None


class AuditSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    severity_min: str = "info"
    sinks: list[str] = Field(default_factory=lambda: ["postgres"])
    retention_days: int | None = None


class ToolAllowlist(BaseModel):
    """Permitted tool / function-call invocations (G6).

    A request whose policy carries a tool allowlist is checked
    post-upstream: any tool_call whose name isn't on ``allow`` (or which
    matches ``deny``) is stripped from the response, the response status
    is rewritten to indicate enforcement, and the violation is audited
    with a ``policy.tool_calls.blocked_total`` counter increment.

    ``deny`` takes precedence over ``allow``. ``allow=["*"]`` means
    "permit anything not on deny". An empty ``allow`` with a non-empty
    ``deny`` is the most common operator config (default-allow with a
    blacklist).
    """

    model_config = ConfigDict(extra="forbid")

    allow: list[str] = Field(default_factory=lambda: ["*"])
    deny: list[str] = Field(default_factory=list)
    # When a disallowed tool is invoked: "redact" (strip the tool_call
    # but keep the rest of the response) or "block" (return 422 to the
    # caller, no upstream data forwarded).
    on_violation: Literal["redact", "block"] = "redact"


class DecideSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[Rule]


class PolicySpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    match: MatchSpec = Field(default_factory=MatchSpec)
    detect: DetectSpec = Field(default_factory=DetectSpec)
    decide: DecideSpec
    route: RouteOverride | None = None
    fail_mode: Literal["open", "closed"] = "closed"
    audit: AuditSpec = Field(default_factory=AuditSpec)
    tool_allowlist: ToolAllowlist | None = None
    # Enforcement mode. "enforce" (default) honours decisions; "shadow" logs
    # the decision but always allows the request to proceed (no blocking, no
    # transforms applied). "monitor" is reserved as an alias for shadow.
    mode: Literal["enforce", "shadow", "monitor"] = "enforce"


class PolicyMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    owner: str | None = None
    description: str | None = None
    version: str = "0"


class Policy(BaseModel):
    model_config = ConfigDict(extra="allow")

    apiVersion: str
    kind: Literal["Policy"]
    metadata: PolicyMeta
    spec: PolicySpec


# ---------------------------------------------------------------------------
# Decision context & decision
# ---------------------------------------------------------------------------


class PrincipalCtx(BaseModel):
    user_id: str
    tenant_id: str
    groups: list[str] = Field(default_factory=list)
    country: str | None = None
    device_id: str | None = None
    ip: str | None = None


class ModelRequestCtx(BaseModel):
    provider: str | None = None
    model: str | None = None


class DecisionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    principal: PrincipalCtx
    route: str
    model_request: ModelRequestCtx = Field(default_factory=ModelRequestCtx)
    headers: dict[str, str] = Field(default_factory=dict)
    jurisdiction: str | None = None
    time: datetime
    request_id: str


class Decision(BaseModel):
    """Outcome of the policy engine for a single request."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["allow", "transform", "block"]
    transforms: list[Transform] = Field(default_factory=list)
    policy_id: str | None = None
    policy_version: str | None = None
    rule_index: int | None = None
    reason: str | None = None
    severity: str | None = None
    fail_mode: Literal["open", "closed"] = "closed"
    upstream_override: str | None = None
    sinks: list[str] = Field(default_factory=lambda: ["postgres"])
    mode: Literal["enforce", "shadow", "monitor"] = "enforce"

    @property
    def is_shadow(self) -> bool:
        return self.mode in ("shadow", "monitor")

    @property
    def effective_action(self) -> Literal["allow", "transform", "block"]:
        """The action that the gateway actually enforces.

        In shadow/monitor mode the decision is logged as ``block``/``transform``
        but the gateway forwards as if it were ``allow``.
        """
        if self.is_shadow:
            return "allow"
        return self.action

    @classmethod
    def allow_default(cls) -> Decision:
        return cls(action="allow", reason="no policy matched")
