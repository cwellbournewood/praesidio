"""Locust soak / load test for Praesidio gateway.

Three user classes mix the same three scenarios used by the perf baseline:

  * ``ShortChatUser`` — 32-token prompts, non-streaming
  * ``LongChatUser``  — ~1k-token prompts, non-streaming
  * ``StreamChatUser`` — ~1k-token prompts with ``stream=true``

Default mix (weights): 5 / 3 / 2. Override via env:

    LOCUST_SHORT_WEIGHT=5 LOCUST_LONG_WEIGHT=3 LOCUST_STREAM_WEIGHT=2

Target the gateway with ``--host http://localhost:8080`` (Locust flag) or via
the ``PRAESIDIO_HOST`` env (used by the wrapper script).

Auth: set ``PRAESIDIO_API_KEY`` (default ``praesidio-demo-key``). Each user
sends it as ``X-API-Key``.

To keep numbers comparable with the perf baseline this file uses identical
prompt construction logic.
"""
from __future__ import annotations

import json
import os
import random

from locust import HttpUser, between, events, task

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("PRAESIDIO_API_KEY", "praesidio-demo-key")
TENANT = os.environ.get("PRAESIDIO_TENANT", "default")
MODEL = os.environ.get("PRAESIDIO_MODEL", "gpt-4o-mini")

SHORT_WEIGHT = int(os.environ.get("LOCUST_SHORT_WEIGHT", "5"))
LONG_WEIGHT = int(os.environ.get("LOCUST_LONG_WEIGHT", "3"))
STREAM_WEIGHT = int(os.environ.get("LOCUST_STREAM_WEIGHT", "2"))

# ---------------------------------------------------------------------------
# Prompts (mirror bench/perf/latency_baseline.py)
# ---------------------------------------------------------------------------

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
    return " ".join(_FILLER_WORDS[:24])


def long_prompt() -> str:
    words: list[str] = []
    while len(words) < 750:
        words.extend(_FILLER_WORDS)
    return " ".join(words[:750])


# A subset of users sprinkle PII in to exercise the anonymise path, so the
# DLP pipeline gets a realistic non-zero hit rate over the soak window.
_PII_SAMPLES = [
    "Please email john.doe@example.com about the contract.",
    "My phone number is +1 415-555-2671.",
    "The card on file ends in 4242 (Visa, 4111 1111 1111 1111).",
    "Server IP is 10.0.3.42.",
    "AWS key AKIA1234567890ABCDEF is being rotated.",
]


def _maybe_taint(prompt: str) -> str:
    if random.random() < 0.10:
        return f"{prompt}\n\n{random.choice(_PII_SAMPLES)}"
    return prompt


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _payload(prompt: str, *, stream: bool) -> dict:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }


def _headers() -> dict:
    return {
        "X-API-Key": API_KEY,
        "X-Praesidio-Tenant": TENANT,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------


class ShortChatUser(HttpUser):
    weight = SHORT_WEIGHT
    wait_time = between(0.05, 0.2)

    @task
    def chat_short(self) -> None:
        with self.client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json=_payload(_maybe_taint(short_prompt()), stream=False),
            name="POST /v1/chat/completions [short]",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 403 and r.headers.get("x-praesidio-decision") == "block":
                # Policy block on a PII-tainted prompt — expected, not an error.
                r.success()
            else:
                r.failure(f"status={r.status_code}")


class LongChatUser(HttpUser):
    weight = LONG_WEIGHT
    wait_time = between(0.1, 0.4)

    @task
    def chat_long(self) -> None:
        with self.client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json=_payload(_maybe_taint(long_prompt()), stream=False),
            name="POST /v1/chat/completions [long]",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 403 and r.headers.get("x-praesidio-decision") == "block":
                r.success()
            else:
                r.failure(f"status={r.status_code}")


class StreamChatUser(HttpUser):
    weight = STREAM_WEIGHT
    wait_time = between(0.1, 0.4)

    @task
    def chat_stream(self) -> None:
        with self.client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json=_payload(_maybe_taint(long_prompt()), stream=True),
            name="POST /v1/chat/completions [stream]",
            catch_response=True,
            stream=True,
        ) as r:
            if r.status_code != 200:
                if r.status_code == 403 and r.headers.get("x-praesidio-decision") == "block":
                    r.success()
                else:
                    r.failure(f"status={r.status_code}")
                return
            # Drain the SSE stream so we measure total time-to-last-byte.
            try:
                for _ in r.iter_lines():
                    pass
                r.success()
            except Exception as exc:
                r.failure(f"stream-drain: {exc}")


# ---------------------------------------------------------------------------
# Telemetry hooks: print a one-line JSON summary at the end so it can be
# captured by run-soak.sh and pasted into the report template.
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def _print_summary(environment, **_kwargs):
    stats = environment.stats
    total = stats.total
    summary = {
        "duration_s": int(total.last_request_timestamp - total.start_time)
        if total.last_request_timestamp and total.start_time else 0,
        "requests": total.num_requests,
        "failures": total.num_failures,
        "rps": round(total.total_rps, 2),
        "p50_ms": total.get_response_time_percentile(0.50),
        "p95_ms": total.get_response_time_percentile(0.95),
        "p99_ms": total.get_response_time_percentile(0.99),
    }
    print("LOCUST_SUMMARY " + json.dumps(summary))
