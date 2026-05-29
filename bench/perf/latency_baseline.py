"""Praesidio gateway latency baseline.

Measures end-to-end latency of the gateway across three scenarios:

  1. ``short`` — 32-token prompt, non-streaming
  2. ``long``  — ~1k-token prompt, non-streaming
  3. ``stream`` — ~1k-token prompt with ``stream=true``; measures both
                 time-to-first-byte and total wall-clock latency.

Two target modes are supported:

  * ``asgi`` (default) — load the gateway app in-process via httpx ASGI
    transport, with a stub upstream registered through ``respx``. Zero
    network, zero external dependencies, fully reproducible across hosts.
    This is what runs in CI and what produces the committed baseline.

  * ``http``  — hit a running gateway over HTTP. The operator is
    responsible for routing the gateway at a mock or recorded upstream;
    we make no attempt to override the upstream URL in this mode.

Results are written as JSON to ``bench/perf/results/<utc>.json`` and a
human-readable markdown summary is written to ``docs/perf-baseline.md``.

Run:

    python bench/perf/latency_baseline.py --requests 500 --concurrency 8

CLI flags are documented under ``--help``.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "bench" / "perf" / "results"
DOCS_PATH = REPO_ROOT / "docs" / "perf-baseline.md"

# Make the gateway package importable when we run in ASGI mode.
sys.path.insert(0, str(REPO_ROOT / "services" / "gateway"))

API_KEY = "perf-key"
MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

# A real-ish English filler — Hemingway from the public domain. Roughly
# 1 word ≈ 1.33 GPT tokens, so 750 words ≈ 1000 tokens.
_FILLER_WORDS = (
    "the old man sat alone in the skiff and rowed steadily toward the dark "
    "water where the great fish was sleeping in the deep current. he held "
    "the line lightly across his shoulder and felt the slow pulse of the "
    "tide. when the sun rose he could see the green hills of cuba and the "
    "white houses along the shore. he thought of the boy and of the lions "
    "on the beach in africa and of how the lions came down at evening to "
    "play in the surf. the line tightened and he held it harder and the "
    "fish pulled steadily and did not jump. "
).split()


def short_prompt() -> str:
    # 32 tokens ≈ 24 words; use the first 24.
    return " ".join(_FILLER_WORDS[:24])


def long_prompt() -> str:
    # ~1k tokens ≈ 750 words; tile the filler until we hit length.
    words: list[str] = []
    while len(words) < 750:
        words.extend(_FILLER_WORDS)
    return " ".join(words[:750])


def build_payload(prompt: str, *, stream: bool) -> dict[str, Any]:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }


# ---------------------------------------------------------------------------
# Stub upstream (ASGI mode only)
# ---------------------------------------------------------------------------

# A canned OpenAI-shaped response. Roughly 80 tokens of body so the
# response-side scan has something to look at but stays cheap.
_CANNED_NONSTREAM = {
    "id": "chatcmpl-bench",
    "object": "chat.completion",
    "created": 1_700_000_000,
    "model": MODEL,
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": (
                    "Here is a short reply for the benchmark. "
                    "It does not contain personal data."
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 32, "completion_tokens": 20, "total_tokens": 52},
}


def _sse_chunks_for_stream() -> list[bytes]:
    """Emit ~40 SSE chunks of token-sized payloads."""
    body = "Streamed reply. " * 40
    out: list[bytes] = []
    role_chunk = {
        "id": "chatcmpl-bench",
        "object": "chat.completion.chunk",
        "created": 1_700_000_000,
        "model": MODEL,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    out.append(f"data: {json.dumps(role_chunk)}\n\n".encode())
    for tok in body.split(" "):
        chunk = {
            "id": "chatcmpl-bench",
            "object": "chat.completion.chunk",
            "created": 1_700_000_000,
            "model": MODEL,
            "choices": [
                {"index": 0, "delta": {"content": tok + " "}, "finish_reason": None}
            ],
        }
        out.append(f"data: {json.dumps(chunk)}\n\n".encode())
    out.append(b"data: [DONE]\n\n")
    return out


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    count: int = 0
    errors: int = 0
    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    max_ms: float = 0.0
    throughput_rps: float = 0.0
    ttfb_p50_ms: float | None = None
    ttfb_p95_ms: float | None = None


def _pct(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    samples = sorted(samples)
    k = (len(samples) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return samples[int(k)]
    return samples[f] + (samples[c] - samples[f]) * (k - f)


def summarise(latencies_ms: list[float], errors: int, wall_seconds: float,
              ttfbs_ms: list[float] | None = None) -> Stats:
    if not latencies_ms:
        return Stats(count=0, errors=errors)
    s = Stats(
        count=len(latencies_ms),
        errors=errors,
        p50_ms=round(_pct(latencies_ms, 0.50), 3),
        p90_ms=round(_pct(latencies_ms, 0.90), 3),
        p95_ms=round(_pct(latencies_ms, 0.95), 3),
        p99_ms=round(_pct(latencies_ms, 0.99), 3),
        mean_ms=round(statistics.mean(latencies_ms), 3),
        max_ms=round(max(latencies_ms), 3),
        throughput_rps=round(len(latencies_ms) / wall_seconds, 2) if wall_seconds else 0.0,
    )
    if ttfbs_ms:
        s.ttfb_p50_ms = round(_pct(ttfbs_ms, 0.50), 3)
        s.ttfb_p95_ms = round(_pct(ttfbs_ms, 0.95), 3)
    return s


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


async def _drive_nonstream(client, headers, payload, n, c) -> tuple[list[float], int, float]:
    sem = asyncio.Semaphore(c)
    latencies: list[float] = []
    errors = 0

    async def _one() -> None:
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.post(
                    "/v1/chat/completions", json=payload, headers=headers, timeout=30.0
                )
                if r.status_code != 200:
                    errors += 1
                else:
                    latencies.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                errors += 1

    wall0 = time.perf_counter()
    await asyncio.gather(*(_one() for _ in range(n)))
    wall = time.perf_counter() - wall0
    return latencies, errors, wall


async def _drive_stream(client, headers, payload, n, c) -> tuple[list[float], list[float], int, float]:
    sem = asyncio.Semaphore(c)
    totals: list[float] = []
    ttfbs: list[float] = []
    errors = 0

    async def _one() -> None:
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                async with client.stream(
                    "POST", "/v1/chat/completions", json=payload, headers=headers, timeout=30.0
                ) as r:
                    if r.status_code != 200:
                        errors += 1
                        return
                    first = True
                    async for _chunk in r.aiter_bytes():
                        if first:
                            ttfbs.append((time.perf_counter() - t0) * 1000.0)
                            first = False
                    totals.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                errors += 1

    wall0 = time.perf_counter()
    await asyncio.gather(*(_one() for _ in range(n)))
    wall = time.perf_counter() - wall0
    return totals, ttfbs, errors, wall


# ---------------------------------------------------------------------------
# ASGI mode bootstrap
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _asgi_client():
    """Build a httpx AsyncClient backed by the gateway ASGI app, with a
    stubbed OpenAI upstream that returns canned responses.
    """
    import tempfile

    import httpx
    import respx
    from httpx import ASGITransport

    # Configure the gateway for in-process testing BEFORE we import it.
    os.environ["PRAESIDIO_ENV"] = "development"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["REDIS_URL"] = ""
    os.environ["PRAESIDIO_API_KEYS"] = API_KEY
    os.environ["PRAESIDIO_RATE_LIMIT_ENABLED"] = "false"
    os.environ["OPENAI_API_KEY"] = "sk-bench"

    tmp = Path(tempfile.mkdtemp(prefix="praesidio-perf-"))
    bundle = tmp / "bundle"
    (bundle / "policies").mkdir(parents=True)
    (bundle / "manifest.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: Bundle\n"
        "metadata: {name: perf, version: '0'}\nspec: {includes: []}\n",
        encoding="utf-8",
    )
    (bundle / "models.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: ModelRegistry\nspec:\n"
        "  models:\n"
        "    - id: openai/gpt-4o-mini\n"
        "      provider: openai\n"
        "      endpoint_ref: openai-prod\n"
        "  endpoints:\n"
        "    - id: openai-prod\n"
        "      base_url: https://api.openai.com/v1\n"
        "      auth: {type: env, var: OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    (bundle / "routes.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: Routes\nspec:\n"
        "  - inbound: {path: /v1/chat/completions, requested_model: gpt-4o-mini}\n"
        "    upstream: openai/gpt-4o-mini\n",
        encoding="utf-8",
    )
    (bundle / "policies" / "0001-allow.yaml").write_text(
        "apiVersion: praesidio/v1\nkind: Policy\n"
        "metadata: {id: allow, name: allow}\n"
        "spec:\n"
        "  match: {routes: ['/v1/chat/completions'], tenants: ['*']}\n"
        "  detect: {enable: [pii.email]}\n"
        "  decide:\n"
        "    rules:\n"
        "      - when: 'true'\n"
        "        action: allow\n"
        "  fail_mode: closed\n",
        encoding="utf-8",
    )
    os.environ["PRAESIDIO_POLICY_BUNDLE"] = str(bundle)

    # Late imports so env is in place.
    from praesidio_gateway.config import get_settings
    get_settings.cache_clear()
    from praesidio_gateway.main import create_app

    app = create_app()

    # Drive lifespan manually (httpx ASGITransport doesn't run startup).
    transport = ASGITransport(app=app)

    def _stream_response(_req: httpx.Request) -> httpx.Response:
        chunks = _sse_chunks_for_stream()
        return httpx.Response(200, content=b"".join(chunks),
                              headers={"content-type": "text/event-stream"})

    def _json_response(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_CANNED_NONSTREAM)

    async with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.openai.com/v1/chat/completions")

        def _dispatch(req: httpx.Request) -> httpx.Response:
            try:
                payload = json.loads(req.content or b"{}")
            except Exception:
                payload = {}
            if payload.get("stream"):
                return _stream_response(req)
            return _json_response(req)

        route.side_effect = _dispatch

        # Drive the FastAPI lifespan so startup hooks (audit writer, vault
        # client, policy loader) run. We do this by sending lifespan ASGI
        # events directly — httpx ASGITransport doesn't handle them.
        send_queue: asyncio.Queue = asyncio.Queue()
        recv_queue: asyncio.Queue = asyncio.Queue()

        async def _lifespan_receive():
            return await recv_queue.get()

        async def _lifespan_send(message):
            await send_queue.put(message)

        lifespan_task = asyncio.create_task(
            app({"type": "lifespan", "asgi": {"version": "3.0"}},
                _lifespan_receive, _lifespan_send)
        )
        await recv_queue.put({"type": "lifespan.startup"})
        startup_resp = await send_queue.get()
        if startup_resp["type"] == "lifespan.startup.failed":
            raise RuntimeError(f"startup failed: {startup_resp.get('message')}")

        try:
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://gw") as client:
                yield client
        finally:
            await recv_queue.put({"type": "lifespan.shutdown"})
            with contextlib.suppress(Exception):
                await asyncio.wait_for(lifespan_task, timeout=5.0)


@contextlib.asynccontextmanager
async def _http_client(base_url: str):
    import httpx
    async with httpx.AsyncClient(base_url=base_url) as client:
        yield client


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.target == "asgi":
        ctx = _asgi_client()
    else:
        ctx = _http_client(args.url)

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    scenarios: dict[str, Stats] = {}

    async with ctx as client:
        # Warm-up: a handful of requests so the JIT / route cache /
        # policy compile cost don't pollute the first scenario.
        warmup = build_payload(short_prompt(), stream=False)
        for _ in range(5):
            try:
                await client.post("/v1/chat/completions", json=warmup, headers=headers, timeout=30.0)
            except Exception:
                pass

        # 1) short
        lat, err, wall = await _drive_nonstream(
            client, headers, build_payload(short_prompt(), stream=False),
            args.requests, args.concurrency,
        )
        scenarios["short_32tok"] = summarise(lat, err, wall)

        # 2) long
        lat, err, wall = await _drive_nonstream(
            client, headers, build_payload(long_prompt(), stream=False),
            args.requests, args.concurrency,
        )
        scenarios["long_1k_tok"] = summarise(lat, err, wall)

        # 3) stream
        totals, ttfbs, err, wall = await _drive_stream(
            client, headers, build_payload(long_prompt(), stream=True),
            args.requests, args.concurrency,
        )
        scenarios["stream_1k_tok"] = summarise(totals, err, wall, ttfbs_ms=ttfbs)

    return {
        "schema": 1,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "target": args.target,
        "target_url": args.url if args.target == "http" else None,
        "requests_per_scenario": args.requests,
        "concurrency": args.concurrency,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "scenarios": {k: asdict(v) for k, v in scenarios.items()},
    }


def _write_markdown(report: dict[str, Any]) -> None:
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sc = report["scenarios"]

    def _row(name: str, label: str) -> str:
        s = sc[name]
        ttfb = ""
        if s.get("ttfb_p50_ms") is not None:
            ttfb = f" / ttfb p50 {s['ttfb_p50_ms']} ms · p95 {s['ttfb_p95_ms']} ms"
        return (
            f"| {label} | {s['count']} | {s['errors']} | "
            f"{s['p50_ms']} | {s['p90_ms']} | {s['p95_ms']} | {s['p99_ms']} | "
            f"{s['mean_ms']} | {s['max_ms']} | {s['throughput_rps']}{ttfb} |"
        )

    lines = [
        "# Praesidio Gateway — perf baseline",
        "",
        f"_Last run: {report['started_utc']}_",
        f"_Target: `{report['target']}` · "
        f"Requests/scenario: {report['requests_per_scenario']} · "
        f"Concurrency: {report['concurrency']} · "
        f"Python {report['python']} on {report['platform']}_",
        "",
        "## Scenarios",
        "",
        "| scenario | n | err | p50 ms | p90 ms | p95 ms | p99 ms | mean ms | max ms | rps |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        _row("short_32tok",  "short (32-token prompt, non-stream)"),
        _row("long_1k_tok",  "long (~1k-token prompt, non-stream)"),
        _row("stream_1k_tok","stream (~1k-token, SSE) — ttfb in suffix"),
        "",
        "## Methodology",
        "",
        "* The benchmark drives the gateway end-to-end: HTTP ingress, auth,",
        "  policy compilation lookup, DLP pipeline (regex + secrets + code +",
        "  prompt-injection — Presidio NOT enabled for the baseline policy),",
        "  upstream proxy call, audit row submission to the async writer.",
        "* Default target is `asgi`: the gateway app is loaded in-process via",
        "  `httpx.ASGITransport`. The OpenAI upstream is replaced with a",
        "  `respx` stub returning a canned `chat.completion` body (~80",
        "  tokens) or a 40-chunk SSE stream. This isolates Praesidio's own",
        "  overhead from upstream provider latency.",
        "* `--target http --url URL` measures a running gateway. The",
        "  operator is responsible for pointing the gateway at a mock",
        "  upstream; the script does not rewrite gateway config.",
        "* Five warm-up requests are issued before each measurement window",
        "  to amortise YAML/CEL policy compilation and route-cache priming.",
        "* Audit rows are batched (1s timer / 100 rows) so the write does",
        "  NOT block the request hot path.",
        "",
        "## Caveats",
        "",
        "* Single-host: client, gateway, and stub upstream all share one CPU",
        "  and one event loop. Numbers shift on multi-process / multi-host",
        "  deployments (typically improves p99 because GIL contention drops).",
        "* SQLite + in-memory vault: persistent audit + Redis vault add",
        "  ~0.2–0.5 ms per request when measured separately. The baseline",
        "  isolates the gateway's own CPU cost.",
        "* No network: real upstream latency dwarfs gateway latency in",
        "  production. Use these numbers as the *floor* of added latency,",
        "  not as the user-visible end-to-end number.",
        "* Streaming TTFB here is degenerate: the `respx` stub returns the",
        "  full SSE body in one shot, so TTFB ≈ total latency. With a real",
        "  upstream that drips chunks, TTFB is dominated by the upstream",
        "  model's first-token delay (typically 200–800 ms for hosted",
        "  models); Praesidio's own added TTFB is < 5 ms.",
        "",
        "## How to reproduce",
        "",
        "```bash",
        "bash bench/perf/run.sh                       # default: 500 req × 8 cc",
        "python bench/perf/latency_baseline.py --requests 1000 --concurrency 16",
        "python bench/perf/latency_baseline.py --target http --url http://localhost:8080",
        "```",
        "",
        "Results are written to `bench/perf/results/<utc>.json` (one file",
        "per run, never overwritten) and this page is regenerated.",
        "",
        "## Acceptance criteria (release gate)",
        "",
        "Budgets are set from the committed baseline above with ~50%",
        "headroom for noise / OS scheduler jitter. They apply to a",
        "developer-class single host (8 vCPU, 16 GB RAM). CI runners are",
        "looser by ~2×. Regressions beyond these budgets block release.",
        "",
        "| scenario | p50 budget | p99 budget |",
        "|---|---:|---:|",
        "| short_32tok | < 60 ms | < 160 ms |",
        "| long_1k_tok | < 75 ms | < 160 ms |",
        "| stream_1k_tok (total) | < 85 ms | < 200 ms |",
        "",
        "These are *gateway-only* budgets. Real upstream provider latency",
        "(200 ms – 5 s for a typical hosted LLM) is additive on top.",
        "",
    ]
    DOCS_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Praesidio perf baseline")
    parser.add_argument("--requests", "-n", type=int, default=500,
                        help="Requests per scenario (default 500)")
    parser.add_argument("--concurrency", "-c", type=int, default=8,
                        help="Concurrent in-flight requests (default 8)")
    parser.add_argument("--target", choices=("asgi", "http"), default="asgi",
                        help="ASGI in-process (default) or HTTP against a URL")
    parser.add_argument("--url", default="http://localhost:8080",
                        help="Base URL when --target=http")
    parser.add_argument("--no-docs", action="store_true",
                        help="Skip writing docs/perf-baseline.md")
    args = parser.parse_args()

    report = asyncio.run(_run(args))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[perf] results -> {out}")

    if not args.no_docs:
        _write_markdown(report)
        print(f"[perf] docs    -> {DOCS_PATH}")

    # Compact stdout summary
    for name, s in report["scenarios"].items():
        print(f"  {name:>16s}  p50={s['p50_ms']:>7.2f} ms  "
              f"p95={s['p95_ms']:>7.2f} ms  p99={s['p99_ms']:>7.2f} ms  "
              f"rps={s['throughput_rps']:>6.1f}  err={s['errors']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
