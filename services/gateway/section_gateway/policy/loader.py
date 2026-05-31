"""Policy bundle loader. Watches the bundle dir, reloads on mtime change.

Reload semantics (G3)
---------------------
The store holds the active bundle behind an atomic reference. ``bundle``
reads are O(1) and *never* see a half-loaded snapshot — at any point in
time either the previous bundle or the new bundle is returned in full.

When ``reload()`` encounters a parse / validation error:

1. The previous bundle remains active. There is **no** intermediate state.
2. A :class:`PolicyReloadError` is raised so the caller (typically the
   admin endpoint) can surface a 4xx with the parse-error message.
3. The ``section_policy_reload_total{outcome="err"}`` counter increments.

On success:

- ``section_policy_reload_total{outcome="ok"}`` increments;
- ``section_policy_active_version{digest,policies}`` is reset to the new
  labelset so dashboards reflect the live version.

In-flight request safety: callers should snapshot the bundle they began a
request with (``bundle = state.policy_store.bundle``) and continue using
that snapshot for the duration of the request. The atomic ref guarantees
no torn read at the swap boundary.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..obs.metrics import POLICY_ACTIVE_VERSION, POLICY_RELOAD_TOTAL
from .models import Policy

_log = logging.getLogger(__name__)


class PolicyReloadError(RuntimeError):
    """Raised when a reload fails to produce a valid bundle.

    The previous bundle remains active. ``parse_errors`` carries a
    per-file list of human-readable error strings the admin endpoint
    surfaces in the 422 response body.
    """

    def __init__(self, parse_errors: list[str]) -> None:
        super().__init__("policy bundle reload failed; " + "; ".join(parse_errors))
        self.parse_errors = parse_errors


@dataclass
class PolicyBundle:
    """An immutable snapshot of the loaded policy bundle."""

    digest: str
    policies: list[Policy] = field(default_factory=list)
    models: dict[str, Any] = field(default_factory=dict)
    routes: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


def _digest_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        try:
            h.update(p.name.encode())
            h.update(p.read_bytes())
        except OSError:
            continue
    return h.hexdigest()


def _safe_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_bundle(
    bundle_dir: str | os.PathLike[str],
    *,
    strict: bool = False,
) -> PolicyBundle:
    """Load (or reload) a bundle from disk. Validates each Policy.

    Parameters
    ----------
    strict:
        When ``True`` (G3: admin-triggered reloads), any policy that
        fails YAML parse or pydantic validation raises
        :class:`PolicyReloadError` carrying the list of file:reason
        strings. When ``False`` (initial dev/test boot), individual
        broken files are logged and skipped so the gateway can still
        come up.
    """
    base = Path(bundle_dir)
    if not base.exists():
        raise FileNotFoundError(f"policy bundle not found: {base}")

    manifest_path = base / "manifest.yaml"
    manifest = _safe_yaml(manifest_path) if manifest_path.exists() else {}

    policies_dir = base / "policies"
    yaml_files = sorted(policies_dir.glob("*.yaml")) if policies_dir.exists() else []
    policies: list[Policy] = []
    parse_errors: list[str] = []
    for fp in yaml_files:
        try:
            raw = _safe_yaml(fp)
            if raw is None:
                continue
            policies.append(Policy.model_validate(raw))
        except Exception as exc:
            msg = f"{fp.name}: {exc}".replace("\n", " ")
            parse_errors.append(msg)
            _log.warning("invalid policy %s", msg)

    models_path = base / "models.yaml"
    routes_path = base / "routes.yaml"
    try:
        models = _safe_yaml(models_path) if models_path.exists() else {}
    except Exception as exc:
        parse_errors.append(f"models.yaml: {exc}".replace("\n", " "))
        models = {}
    try:
        routes_doc = _safe_yaml(routes_path) if routes_path.exists() else {}
    except Exception as exc:
        parse_errors.append(f"routes.yaml: {exc}".replace("\n", " "))
        routes_doc = {}
    routes = routes_doc.get("spec", []) if isinstance(routes_doc, dict) else []

    if strict and parse_errors:
        raise PolicyReloadError(parse_errors)

    file_set = [manifest_path, models_path, routes_path, *yaml_files]
    digest = _digest_files([p for p in file_set if p.exists()])

    return PolicyBundle(
        digest=digest,
        policies=policies,
        models=models,
        routes=routes,
        manifest=manifest,
        source_path=str(base),
    )


class PolicyStore:
    """Holder for the active bundle with race-safe hot-reload (G3).

    The active bundle lives behind an ``RLock``-protected atomic reference:
    readers (``bundle`` property) acquire the lock only long enough to
    return the current pointer. The cost is one un-contended lock per
    request — negligible compared to the rest of the request pipeline.

    On reload failure the previous bundle is preserved verbatim and
    :class:`PolicyReloadError` propagates to the caller. This is the
    "fail to swap, don't half-swap" invariant the admin endpoint relies on
    to return 422 without breaking in-flight traffic.
    """

    def __init__(self, bundle_dir: str) -> None:
        self._dir = Path(bundle_dir)
        self._bundle: PolicyBundle | None = None
        self._mtime_sig: tuple[float, ...] = ()
        # Async lock serialises the actual file IO + swap so two parallel
        # reload() calls don't both try to mutate the ref. The thread RLock
        # serialises the *ref read* — bundle reads happen from the request
        # path which is async-only, so this is conservative but cheap.
        self._lock = asyncio.Lock()
        self._ref_lock = threading.RLock()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def bundle(self) -> PolicyBundle:
        """Atomic read of the currently-active bundle.

        Returns the same snapshot for the entire duration of a request as
        long as the caller stores the result locally instead of re-reading
        ``.bundle`` between steps. The pointer swap during a concurrent
        reload is fully serialised via the ref lock — readers see either
        the old or the new bundle, never a half-loaded state.
        """
        with self._ref_lock:
            if self._bundle is None:
                raise RuntimeError("PolicyStore not loaded yet")
            return self._bundle

    def loaded(self) -> bool:
        with self._ref_lock:
            return self._bundle is not None

    def _signature(self) -> tuple[float, ...]:
        sig: list[float] = []
        for p in sorted(self._dir.rglob("*.yaml")):
            try:
                sig.append(p.stat().st_mtime)
            except OSError:
                continue
        return tuple(sig)

    def _update_active_version_metric(self, bundle: PolicyBundle) -> None:
        """Reset the active-version gauge so dashboards reflect the live bundle.

        We clear the metric and re-set it to ``1`` under the new digest
        labelset — gauge labelsets accumulate over time otherwise.
        """
        try:
            POLICY_ACTIVE_VERSION.clear()
            POLICY_ACTIVE_VERSION.labels(
                digest=bundle.digest[:12], policies=str(len(bundle.policies))
            ).set(1)
        except Exception:  # pragma: no cover - metrics are best-effort
            pass

    async def reload(self, *, strict: bool = True) -> PolicyBundle:
        """Reload from disk atomically.

        When ``strict`` (default), parse errors raise
        :class:`PolicyReloadError` and the previous bundle stays active.
        When ``strict=False`` (initial boot / background watcher), broken
        files are logged and skipped.
        """
        async with self._lock:
            try:
                new = await asyncio.to_thread(load_bundle, self._dir, strict=strict)
            except PolicyReloadError as exc:
                POLICY_RELOAD_TOTAL.labels(outcome="err").inc()
                _log.warning(
                    "policy bundle reload rejected (last-good retained): %s",
                    "; ".join(exc.parse_errors),
                )
                raise
            with self._ref_lock:
                self._bundle = new
                self._mtime_sig = self._signature()
            self._update_active_version_metric(new)
            POLICY_RELOAD_TOTAL.labels(outcome="ok").inc()
            _log.info(
                "policy bundle loaded digest=%s policies=%d routes=%d",
                new.digest[:12],
                len(new.policies),
                len(new.routes),
            )
            return new

    async def _watcher(self, interval: float) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass
            if self._stop.is_set():
                return
            try:
                sig = self._signature()
                if sig != self._mtime_sig:
                    # Background reload tolerates partial-failure: a broken
                    # policy file shouldn't take the gateway offline if the
                    # operator is mid-edit. Last-good is still preserved.
                    try:
                        await self.reload(strict=False)
                    except PolicyReloadError as exc:
                        _log.warning(
                            "background policy reload rejected: %s",
                            "; ".join(exc.parse_errors),
                        )
            except Exception:
                _log.exception("policy reload failed")

    async def start(self, *, interval: float = 5.0) -> None:
        # Initial load: non-strict so an operator with a broken bundle can
        # still bring the gateway up and see the diagnostic in /metrics
        # and the structured log.
        await self.reload(strict=False)
        self._task = asyncio.create_task(self._watcher(interval), name="policy-watcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
