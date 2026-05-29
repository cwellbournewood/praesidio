/**
 * Light-weight extension tests — exercise the pieces that don't need
 * a live VS Code host (decision store, status bar, OIDC tenant claim
 * decoding).
 */
import "./vscode-mock.js";

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { DecisionStore } from "../src/decisionsView.js";
import { decodeTenantClaim } from "../src/auth.js";

describe("DecisionStore", () => {
  it("keeps decisions newest-first", () => {
    const s = new DecisionStore();
    s.push({
      request_id: "1",
      action: "allow",
      reason: null,
      severity: null,
      uri: null,
      occurredAt: "2026-01-01T00:00:00Z",
      findingCount: 0,
      transformCount: 0,
      excerpt: "first",
    });
    s.push({
      request_id: "2",
      action: "mask",
      reason: null,
      severity: null,
      uri: null,
      occurredAt: "2026-01-01T00:00:01Z",
      findingCount: 2,
      transformCount: 2,
      excerpt: "second",
    });
    const list = s.list();
    assert.equal(list.length, 2);
    assert.equal(list[0]!.request_id, "2");
    assert.equal(s.last()!.request_id, "2");
  });

  it("caps the buffer at 50", () => {
    const s = new DecisionStore();
    for (let i = 0; i < 75; i++) {
      s.push({
        request_id: String(i),
        action: "allow",
        reason: null,
        severity: null,
        uri: null,
        occurredAt: "",
        findingCount: 0,
        transformCount: 0,
        excerpt: "",
      });
    }
    assert.equal(s.list().length, 50);
    // The most recent push wins.
    assert.equal(s.list()[0]!.request_id, "74");
  });

  it("fires change events", () => {
    const s = new DecisionStore();
    let fired = 0;
    const sub = s.onDidChange(() => fired++);
    s.push({
      request_id: "x",
      action: "allow",
      reason: null,
      severity: null,
      uri: null,
      occurredAt: "",
      findingCount: 0,
      transformCount: 0,
      excerpt: "",
    });
    s.clear();
    assert.equal(fired, 2);
    sub.dispose();
    s.dispose();
  });
});

describe("decodeTenantClaim", () => {
  it("extracts a tenant claim from a JWT payload", () => {
    const header = base64url(JSON.stringify({ alg: "none" }));
    const payload = base64url(JSON.stringify({ praesidio_tenant: "acme" }));
    const jwt = `${header}.${payload}.sig`;
    assert.equal(decodeTenantClaim(jwt), "acme");
  });

  it("returns undefined for malformed tokens", () => {
    assert.equal(decodeTenantClaim(""), undefined);
    assert.equal(decodeTenantClaim("abc"), undefined);
    assert.equal(decodeTenantClaim("a.b.c.d"), undefined);
  });

  it("falls back to 'tenant' and 'tid' claims", () => {
    const header = base64url(JSON.stringify({ alg: "none" }));
    const payload = base64url(JSON.stringify({ tid: "globex" }));
    const jwt = `${header}.${payload}.sig`;
    assert.equal(decodeTenantClaim(jwt), "globex");
  });
});

function base64url(s: string): string {
  return Buffer.from(s, "utf-8").toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}
