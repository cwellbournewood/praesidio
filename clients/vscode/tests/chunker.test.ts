/**
 * Unit tests for the document chunker.
 */
import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { chunkDocument } from "../src/lib/chunker.js";

describe("chunkDocument", () => {
  it("returns empty for empty input", () => {
    assert.deepEqual(chunkDocument(""), []);
  });

  it("returns one chunk when the document fits", () => {
    const text = "hello\nworld";
    const chunks = chunkDocument(text, 1024);
    assert.equal(chunks.length, 1);
    assert.equal(chunks[0]!.text, text);
    assert.equal(chunks[0]!.startOffset, 0);
  });

  it("splits on line boundaries when over the byte cap", () => {
    const line = "x".repeat(100) + "\n";
    const text = line.repeat(10);
    const chunks = chunkDocument(text, 250);
    assert.ok(chunks.length >= 2);
    // Every chunk should be <= 250 bytes.
    for (const c of chunks) {
      assert.ok(c.byteLength <= 250, `chunk too big: ${c.byteLength}`);
    }
    // Concatenating chunks must reproduce the original document.
    const recon = chunks.map((c) => c.text).join("");
    assert.equal(recon, text);
    // Offsets must be monotonic.
    let prev = -1;
    for (const c of chunks) {
      assert.ok(c.startOffset > prev);
      prev = c.startOffset;
    }
  });

  it("hard-splits a single oversize line on byte boundaries", () => {
    const text = "a".repeat(1000);
    const chunks = chunkDocument(text, 300);
    assert.ok(chunks.length >= 4);
    for (const c of chunks) {
      assert.ok(c.byteLength <= 300);
    }
    assert.equal(chunks.map((c) => c.text).join(""), text);
  });

  it("never splits a multi-byte UTF-8 codepoint", () => {
    // Each emoji is 4 UTF-8 bytes — 100 emoji = 400 bytes.
    const text = "🛡️".repeat(100);
    const chunks = chunkDocument(text, 50);
    for (const c of chunks) {
      assert.ok(c.byteLength <= 50);
      // The recomposed segment must be valid UTF-8 (round-trip via Buffer).
      const round = Buffer.from(c.text, "utf-8").toString("utf-8");
      assert.equal(round, c.text);
    }
    assert.equal(chunks.map((c) => c.text).join(""), text);
  });

  it("rejects non-positive maxBytes", () => {
    assert.throws(() => chunkDocument("x", 0));
    assert.throws(() => chunkDocument("x", -10));
  });
});
