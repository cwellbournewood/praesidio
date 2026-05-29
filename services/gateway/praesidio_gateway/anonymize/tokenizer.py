"""Tokeniser: turns Findings + Transforms into a sanitised string + reversal map.

Placeholder grammar (per `docs/architecture/05-anonymization.md`):
    <LABEL_xxxx>    – 4-char base32 hash of (tenant, scope_key, original)

Identical originals within the same scope receive the same placeholder, so
session/tenant scope produces consistent aliases.
"""
from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..policy.models import Finding, Transform
from .fpe import FPEUnavailable
from .fpe import encrypt as fpe_encrypt
from .redactor import redact_label
from .vault import TokenVault

# A placeholder, as it appears in the sanitised request.
_PLACEHOLDER_RE = re.compile(r"<([A-Z][A-Z0-9_]*)_([A-Z2-7]{4})>")


@dataclass
class ReversalEntry:
    placeholder: str
    original: str
    label: str
    method: str
    scope: str
    ttl_seconds: int


@dataclass
class ReversalMap:
    request_id: str
    tenant_id: str
    entries: list[ReversalEntry] = field(default_factory=list)
    # Fast O(1) lookup for the restore stream.
    by_placeholder: dict[str, str] = field(default_factory=dict)

    def add(self, entry: ReversalEntry) -> None:
        self.entries.append(entry)
        self.by_placeholder.setdefault(entry.placeholder, entry.original)


def _label_short(label: str) -> str:
    """Placeholder fragment for `label`, e.g. `<ORGANIZATION_A2F4>`.

    Sources the short name from `dlp.display.LABELS` so the placeholder
    grammar stays in lock-step with the operator-facing display names.
    Falls back to a UPPER_SNAKE version of the label for unknown entries.
    """
    from ..dlp.display import short_for

    return short_for(label)


def _placeholder(label: str, scope_key: str, original: str) -> str:
    short = _label_short(label)
    digest = hashlib.sha256(f"{scope_key}|{original}".encode()).digest()
    suffix = base64.b32encode(digest)[:4].decode("ascii").upper()
    return f"<{short}_{suffix}>"


def _scope_key(*, tenant: str, request_id: str, scope: str) -> str:
    if scope == "tenant":
        return f"tenant:{tenant}"
    if scope == "session":
        # In the simplest implementation, "session" reuses the tenant prefix +
        # the request id's stable prefix; downstream session handling can pass
        # an explicit session id in DecisionContext.headers.
        return f"sess:{tenant}:{request_id}"
    return f"req:{tenant}:{request_id}"


def _ttl_to_seconds(ttl: str | None, default: int = 3600) -> int:
    if not ttl:
        return default
    s = ttl.strip().lower()
    try:
        if s.endswith("h"):
            return int(float(s[:-1]) * 3600)
        if s.endswith("m"):
            return int(float(s[:-1]) * 60)
        if s.endswith("s"):
            return int(float(s[:-1]))
        return int(s)
    except ValueError:
        return default


def _transforms_by_label(transforms: Iterable[Transform]) -> dict[str, Transform]:
    return {t.label: t for t in transforms}


@dataclass
class AnonymiseResult:
    sanitised: str
    reversal: ReversalMap
    applied: list[dict]


def _slice_text(text: str, findings: list[Finding]) -> list[tuple[int, int, Finding | None]]:
    """Return (start, end, finding-or-None) intervals covering text in order.

    Findings overlap-resolved by greedy left-to-right; later overlapping
    findings are dropped.
    """
    chosen: list[Finding] = []
    cursor = 0
    for f in sorted(findings, key=lambda x: (x.start, -x.end)):
        if f.start < cursor:
            continue
        chosen.append(f)
        cursor = f.end

    out: list[tuple[int, int, Finding | None]] = []
    pos = 0
    for f in chosen:
        if pos < f.start:
            out.append((pos, f.start, None))
        out.append((f.start, f.end, f))
        pos = f.end
    if pos < len(text):
        out.append((pos, len(text), None))
    return out


async def anonymise(
    *,
    text: str,
    findings: list[Finding],
    transforms: list[Transform],
    tenant_id: str,
    request_id: str,
    vault: TokenVault,
    default_ttl_seconds: int = 3600,
) -> AnonymiseResult:
    """Apply the policy's transforms to `text`, returning the sanitised string."""
    rev = ReversalMap(request_id=request_id, tenant_id=tenant_id)
    by_label = _transforms_by_label(transforms)
    out_parts: list[str] = []
    applied: list[dict] = []

    for start, end, f in _slice_text(text, findings):
        if f is None:
            out_parts.append(text[start:end])
            continue
        t = by_label.get(f.label)
        if t is None:
            # No transform for this label — leave as-is.
            out_parts.append(text[start:end])
            continue
        original = text[start:end]
        if t.method == "redact":
            replacement = redact_label(f.label, t.replacement)
        elif t.method == "fpe":
            try:
                replacement = fpe_encrypt(
                    key=b"\x00" * 16,
                    tweak=b"\x00" * 7,
                    alphabet="0123456789",
                    plaintext="".join(c for c in original if c.isdigit()) or "0000000",
                )
            except FPEUnavailable:
                # Fall back to tokenise if FPE backend isn't wired.
                replacement = _placeholder(
                    f.label, _scope_key(tenant=tenant_id, request_id=request_id, scope=t.scope), original
                )
                ttl_s = _ttl_to_seconds(t.ttl, default_ttl_seconds)
                await vault.put(
                    tenant=tenant_id,
                    request_id=request_id,
                    placeholder=replacement,
                    plaintext=original,
                    ttl_seconds=ttl_s,
                )
                rev.add(
                    ReversalEntry(replacement, original, f.label, "tokenise_fallback", t.scope, ttl_s)
                )
                applied.append(
                    {"label": f.label, "method": "tokenise_fallback", "from": "fpe"}
                )
                out_parts.append(replacement)
                continue
        else:  # tokenise (default)
            scope_key = _scope_key(tenant=tenant_id, request_id=request_id, scope=t.scope)
            replacement = _placeholder(f.label, scope_key, original)
            ttl_s = _ttl_to_seconds(t.ttl, default_ttl_seconds)
            await vault.put(
                tenant=tenant_id,
                request_id=request_id,
                placeholder=replacement,
                plaintext=original,
                ttl_seconds=ttl_s,
            )
            rev.add(ReversalEntry(replacement, original, f.label, "tokenise", t.scope, ttl_s))

        applied.append({"label": f.label, "method": t.method, "scope": t.scope})
        out_parts.append(replacement)

    return AnonymiseResult(sanitised="".join(out_parts), reversal=rev, applied=applied)


# ---------------------------------------------------------------------------
# Restoration (response path)
# ---------------------------------------------------------------------------


def restore_text(text: str, reversal: ReversalMap) -> str:
    """Synchronous restore — used for non-streaming responses."""

    def _sub(m: re.Match[str]) -> str:
        return reversal.by_placeholder.get(m.group(0), m.group(0))

    return _PLACEHOLDER_RE.sub(_sub, text)


async def restore_with_vault(
    text: str, *, tenant: str, request_id: str, vault: TokenVault
) -> str:
    """Asynchronous restore via vault lookups (handles cross-request placeholders)."""

    out: list[str] = []
    pos = 0
    for m in _PLACEHOLDER_RE.finditer(text):
        out.append(text[pos : m.start()])
        ph = m.group(0)
        val = await vault.get(tenant=tenant, request_id=request_id, placeholder=ph)
        out.append(val if val is not None else ph)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)
