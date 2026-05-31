# Recording Real-LLM E2E cassettes

The gateway's CI exercises four representative LLM interactions
(`openai-chat-pii`, `openai-chat-block`, `anthropic-messages-pii`,
`anthropic-messages-block`) on every pull request via
`services/gateway/tests/test_e2e_real_llm.py`. Each interaction is driven
by a JSON **cassette** under `services/gateway/tests/cassettes/`. The
cassette captures:

* the inbound client request (headers + JSON body),
* the upstream URL that the gateway must (or must not) call,
* a templated upstream response (with `{EMAIL_PLACEHOLDER}` substitution),
* a set of expectations: decision, restoration, audit landing.

Because the upstream HTTP layer is mocked via `respx`, **tests never call
OpenAI / Anthropic in CI**. The cassettes still give us realistic request
and response shapes (matching the live JSON schemas) so we catch
regressions in how the gateway parses, anonymises, and restores them.

## When to add or refresh a cassette

* A new upstream provider (e.g. Bedrock, Gemini) is added — capture a
  PII-bearing and a block-bearing interaction per route.
* The upstream changes a response field (e.g. OpenAI adds a new key) and
  the gateway's parser needs to keep up — refresh by re-recording.
* A bug is fixed that previously caused mis-restoration — add a cassette
  that pins the fix.

## How to record a new cassette (the safe way)

1. **Pick a fresh local Postgres + Redis** so you do not pollute prod
   audit. The fastest path is `docker compose up postgres redis` from the
   repo root.

2. **Start a temporary "recorder" gateway** with your real API key, but
   on a sandboxed bundle so production policies are not in play:

   ```bash
   export OPENAI_API_KEY=sk-...          # use a low-spend test key
   export SECTION_API_KEYS=recorder
   export SECTION_POLICY_BUNDLE=$PWD/examples/policies
   export SECTION_ENV=development
   cd services/gateway
   uv run section-gateway
   ```

3. **Send the inbound request you want to capture** through the gateway
   and use `mitmproxy` / a small `httpx` script to **also intercept what
   the gateway sent upstream**:

   ```bash
   mitmdump --mode reverse:https://api.openai.com \
       --listen-port 9999 -w /tmp/upstream.dump
   # ...repoint the gateway to http://localhost:9999 for the recording...
   ```

   Or — simpler — capture both sides with the built-in `/admin/events`
   row. Every audit event records `request_digest`, `response_digest`,
   and `transforms`, and `tests/test_e2e_real_llm.py` only needs the
   *shape* of the upstream response, not the exact body.

4. **Manually compose the cassette JSON** following the template below.
   `body_template` may use `{EMAIL_PLACEHOLDER}` anywhere — the test
   will substitute the actual `<EMAIL_xxxx>` token the gateway used so
   restoration round-trips end-to-end.

   ```json
   {
     "name": "openai-chat-pii",
     "description": "...",
     "provider": "openai",
     "route": "/v1/chat/completions",
     "upstream": {"method": "POST", "url": "https://api.openai.com/v1/chat/completions"},
     "client_request": {
       "headers": {"x-api-key": "test-key", "content-type": "application/json"},
       "body": { ... }
     },
     "upstream_response": {
       "status": 200,
       "headers": {"content-type": "application/json"},
       "body_template": { ... with {EMAIL_PLACEHOLDER} markers ... }
     },
     "policy": "pii_tokenise_email",
     "expectations": {
       "status_code": 200,
       "upstream_must_not_contain": ["alice@example.com"],
       "upstream_must_contain": ["<EMAIL_"],
       "client_must_contain": ["alice@example.com"],
       "client_must_not_contain": ["<EMAIL_"],
       "audit_decision": "transform"
     }
   }
   ```

5. **Wire the policy** into `tests/test_e2e_real_llm.py` under the
   `_POLICIES` dict, keyed by the same `policy` id you used in the
   cassette. Keep policies small and inline — they double as
   self-documenting examples.

6. **Run locally**:

   ```bash
   cd services/gateway
   uv run pytest tests/test_e2e_real_llm.py -v -k <your_cassette_name>
   ```

7. **Sanitise** the recorded data:
   * Strip any auth headers, cookies, or `Authorization` values from the
     cassette JSON.
   * Replace any production tenant IDs, user IDs, or real customer
     emails with `example.com` / `example.org`.
   * Re-grep for prefixes (`sk-`, `AKIA`, JWT-like dot-segments).

## What CI guarantees

* HTTP status code matches `expectations.status_code`.
* The upstream URL was called exactly once (transform path) or never
  (block path).
* No raw PII leaked upstream; placeholder substituted as required.
* The client response restored the original value (or never received it
  on the block path).
* An audit row landed with the expected `decision`.

## Storing the original raw HTTP exchanges (optional)

For provenance / debugging, you may keep the original mitmproxy dumps
under `services/gateway/tests/cassettes/raw/` — git-ignored. The JSON
cassettes are the only files CI consumes.

## Failure modes worth checking

* The placeholder grammar is base32-`[A-Z2-7]{4}`. If you hand-craft a
  fake placeholder, never use `0` or `1` — the regex will not match and
  restoration will look broken.
* The audit writer batches every ~1s; if a test reads audit rows
  immediately after a request, poll with a generous timeout (see
  `_wait_for_audit` in the test module).
