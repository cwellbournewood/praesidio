"""GET /admin/labels — operator-facing display catalogue for DLP labels.

This endpoint exposes the human-readable display metadata that lives in
:mod:`section_gateway.dlp.display`. UIs, dashboards, SIEM pipelines,
and notebooks can fetch the whole catalogue once and render
``finding.label`` as something a human can read.

The endpoint is **unauthenticated and read-only** — there is no
PII, no tenant data, no policy detail in the payload. It's the same
static catalogue the UI ships in ``services/ui/lib/labels.ts`` and is
safe to cache aggressively (an ETag is set off the catalogue size +
hash so consumers can avoid re-fetching unchanged data).
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from fastapi import APIRouter, Response

from ...dlp.display import LABELS, categories

router = APIRouter(prefix="/admin", tags=["admin"])


@lru_cache(maxsize=1)
def _payload() -> tuple[dict, str]:
    """Build the payload + ETag once at first call.

    Cached because the catalogue is static for the lifetime of the
    process (mutations require redeploying the gateway), so we can serve
    it cheaply on hot paths.
    """
    items = [d.to_dict() for d in LABELS.values()]
    body = {
        "version": "1",
        "categories": categories(),
        "labels": items,
        "count": len(items),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return body, digest


@router.get(
    "/labels",
    summary="DLP label display catalogue",
    response_model=None,
)
async def get_labels(response: Response) -> dict:
    """Return the full display catalogue: human name, category, severity,
    description, and an optional example for every wire label the gateway
    can emit.
    """
    body, etag = _payload()
    response.headers["ETag"] = f'"{etag}"'
    # Cache for an hour — the catalogue is process-static, but ops may
    # want to invalidate on rollout, and an hour bounds the staleness.
    response.headers["Cache-Control"] = "public, max-age=3600"
    return body
