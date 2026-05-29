/**
 * Unit tests for the gateway HTTP client.
 *
 * No real network — we inject a `fetchImpl` stub and assert the
 * client formats the request, parses the response, and surfaces error
 * conditions correctly.
 */
import "./vscode-mock.js";

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import {
  GatewayClient,
  GatewayHttpError,
  GatewayNetworkError,
} from "../src/gateway.js";
import type { ScanResponse } from "../src/lib/types.js";

function fakeResponse(body: unknown, init: { status?: number } = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("GatewayClient", () => {
  it("requires baseUrl", () => {
    assert.throws(() => new GatewayClient({ baseUrl: "" }));
  });

  it("normalises trailing slash on baseUrl", () => {
    const c = new GatewayClient({ baseUrl: "http://x.test/" });
    assert.equal(c.baseUrl, "http://x.test");
  });

  it("scan() sends API key header, parses response", async () => {
    const seen: { url: string; init: RequestInit }[] = [];
    const expected: ScanResponse = {
      request_id: "req-1",
      action: "mask",
      sanitised: "<EMAIL_A2B3>",
      transforms: [
        {
          label: "pii.email",
          placeholder: "<EMAIL_A2B3>",
          method: "tokenise",
          scope: "request",
        },
      ],
      findings: [
        {
          label: "pii.email",
          detector: "regex",
          confidence: 0.9,
          start: 0,
          end: 10,
        },
      ],
      decision: {
        action: "transform",
        mode: "enforce",
        effective_action: "transform",
        is_shadow: false,
        policy_id: "p1",
        policy_version: "v1",
        rule_index: 0,
        reason: null,
        severity: null,
      },
      bundle_digest: "abc",
    };
    const fetchImpl = (async (
      url: string,
      init: RequestInit,
    ): Promise<Response> => {
      seen.push({ url, init });
      return fakeResponse(expected);
    }) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    const resp = await client.scan(
      { text: "hi", client: "vscode" },
      { apiKey: "praes_key", tenantId: "acme" },
    );
    assert.equal(seen.length, 1);
    assert.equal(seen[0]!.url, "http://gw.test/v1/scan");
    const headers = seen[0]!.init.headers as Record<string, string>;
    assert.equal(headers["X-API-Key"], "praes_key");
    assert.equal(headers["X-Praesidio-Tenant"], "acme");
    assert.equal(headers["Content-Type"], "application/json");
    assert.equal(resp.request_id, "req-1");
    assert.equal(resp.action, "mask");
  });

  it("scan() prefers API key over bearer", async () => {
    const seen: { headers: Record<string, string> }[] = [];
    const fetchImpl = (async (
      _url: string,
      init: RequestInit,
    ): Promise<Response> => {
      seen.push({ headers: init.headers as Record<string, string> });
      return fakeResponse({
        request_id: "x",
        action: "allow",
        sanitised: null,
        transforms: [],
        findings: [],
        decision: {
          action: "allow",
          mode: "enforce",
          effective_action: "allow",
          is_shadow: false,
          policy_id: null,
          policy_version: null,
          rule_index: null,
          reason: null,
          severity: null,
        },
        bundle_digest: "",
      });
    }) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    await client.scan(
      { text: "hi", client: "vscode" },
      { apiKey: "k1", bearerToken: "b1" },
    );
    assert.equal(seen[0]!.headers["X-API-Key"], "k1");
    assert.ok(!seen[0]!.headers["Authorization"]);
  });

  it("scan() sends Authorization: Bearer when no API key", async () => {
    const seen: { headers: Record<string, string> }[] = [];
    const fetchImpl = (async (
      _url: string,
      init: RequestInit,
    ): Promise<Response> => {
      seen.push({ headers: init.headers as Record<string, string> });
      return fakeResponse({
        request_id: "x",
        action: "allow",
        sanitised: null,
        transforms: [],
        findings: [],
        decision: {
          action: "allow",
          mode: "enforce",
          effective_action: "allow",
          is_shadow: false,
          policy_id: null,
          policy_version: null,
          rule_index: null,
          reason: null,
          severity: null,
        },
        bundle_digest: "",
      });
    }) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    await client.scan(
      { text: "hi", client: "vscode" },
      { bearerToken: "eyJabc.def.ghi" },
    );
    assert.equal(seen[0]!.headers["Authorization"], "Bearer eyJabc.def.ghi");
    assert.ok(!seen[0]!.headers["X-API-Key"]);
  });

  it("scan() raises GatewayHttpError on 5xx", async () => {
    const fetchImpl = (async (): Promise<Response> =>
      new Response("kaboom", { status: 503 })) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    await assert.rejects(
      () => client.scan({ text: "x", client: "vscode" }, {}),
      (err: unknown) => {
        assert.ok(err instanceof GatewayHttpError);
        assert.equal((err as GatewayHttpError).status, 503);
        return true;
      },
    );
  });

  it("scan() wraps fetch errors as GatewayNetworkError", async () => {
    const fetchImpl = (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    await assert.rejects(
      () => client.scan({ text: "x", client: "vscode" }, {}),
      (err: unknown) => {
        assert.ok(err instanceof GatewayNetworkError);
        return true;
      },
    );
  });

  it("restore() returns the parsed response", async () => {
    const fetchImpl = (async (
      _url: string,
      _init: RequestInit,
    ): Promise<Response> =>
      fakeResponse({
        request_id: "r1",
        text: "hello world",
        restored: 1,
        missing: [],
      })) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    const r = await client.restore(
      { request_id: "r1", text: "hello <X_A2B3>" },
      { apiKey: "k" },
    );
    assert.equal(r.restored, 1);
    assert.equal(r.text, "hello world");
  });

  it("health() returns false on any failure", async () => {
    const fetchImpl = (async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;
    const client = new GatewayClient({
      baseUrl: "http://gw.test",
      fetchImpl,
    });
    assert.equal(await client.health(), false);
  });
});
