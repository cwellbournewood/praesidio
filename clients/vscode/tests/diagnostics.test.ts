/**
 * Diagnostic scanner unit tests — exercises the offset-translation
 * helper that maps `findings[].start`/`.end` back into VS Code ranges.
 *
 * The full scanner pipeline (debounced workspace events) needs a real
 * VS Code host; we cover that surface in `extension.test.ts` against
 * @vscode/test-electron only if available. The pure offset logic is
 * tested here.
 */
import "./vscode-mock.js";

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { makeStubDoc } from "./vscode-mock.js";
import { findingRange } from "../src/diagnostics/scanner.js";

describe("diagnostics.findingRange", () => {
  it("translates a finding inside the first chunk", () => {
    const doc = makeStubDoc("hello world\nsecond line");
    const r = findingRange(doc as any, 0, {
      label: "pii.email",
      detector: "regex",
      confidence: 1,
      start: 6,
      end: 11,
    });
    assert.equal(r.start.line, 0);
    assert.equal(r.start.character, 6);
    assert.equal(r.end.line, 0);
    assert.equal(r.end.character, 11);
  });

  it("respects the chunk's startOffset", () => {
    const doc = makeStubDoc("zero\none\ntwo\nthree");
    // Chunk starts at offset 5 ("one\n…"), finding at chunk-relative 4-7
    // is absolute 9-12.
    const r = findingRange(doc as any, 5, {
      label: "x",
      detector: "regex",
      confidence: 1,
      start: 4,
      end: 7,
    });
    // Absolute offset 9 is line 2 char 0; 12 is line 2 char 3.
    assert.equal(r.start.line, 2);
    assert.equal(r.start.character, 0);
    assert.equal(r.end.line, 2);
    assert.equal(r.end.character, 3);
  });
});
