/**
 * Debounced per-document scanner.
 *
 * Scans the contents of any open text document through `/v1/scan`,
 * surfacing each `findings[]` entry as a `vscode.Diagnostic`. We use
 * `scan` rather than a future `/v1/preview` endpoint because that's
 * what the gateway already exposes — but we **do not** auto-apply the
 * returned `sanitised` text. The user must trigger the
 * "Praesidio: Tokenise" code action explicitly.
 *
 * Important: every scan still writes a vault entry + audit row on the
 * server. For very large documents this is fine (scan is idempotent
 * for the same text + session_id), but to limit noise we
 *  - debounce per document URI,
 *  - chunk the text into ~256kB slices, and
 *  - reuse a stable `session_id` per document so retries share a
 *    request_id.
 */

import * as vscode from "vscode";

import { GatewayClient, type Credential } from "../gateway.js";
import { chunkDocument } from "../lib/chunker.js";
import type { ScanFinding } from "../lib/types.js";

export interface ScannerOpts {
  client: GatewayClient;
  diagnostics: vscode.DiagnosticCollection;
  getCredential: () => Promise<Credential>;
  severity: () => vscode.DiagnosticSeverity;
  debounceMs: () => number;
  maxBytes: () => number;
  enabled: () => boolean;
  onScanComplete?: (uri: vscode.Uri, findings: ScanFinding[]) => void;
}

interface PendingScan {
  timer: NodeJS.Timeout;
  version: number;
}

export class DocumentScanner {
  private readonly pending = new Map<string, PendingScan>();
  private readonly sessionByUri = new Map<string, string>();
  private readonly subs: vscode.Disposable[] = [];

  constructor(private readonly opts: ScannerOpts) {
    this.subs.push(
      vscode.workspace.onDidOpenTextDocument((d) => this.schedule(d)),
      vscode.workspace.onDidChangeTextDocument((e) =>
        this.schedule(e.document),
      ),
      vscode.workspace.onDidCloseTextDocument((d) => this.forget(d.uri)),
    );
    // Seed the already-open documents.
    for (const d of vscode.workspace.textDocuments) {
      this.schedule(d);
    }
  }

  dispose(): void {
    for (const p of this.pending.values()) clearTimeout(p.timer);
    this.pending.clear();
    for (const s of this.subs) s.dispose();
  }

  /** Cancel any pending scan + clear diagnostics for `uri`. */
  forget(uri: vscode.Uri): void {
    const key = uri.toString();
    const p = this.pending.get(key);
    if (p) clearTimeout(p.timer);
    this.pending.delete(key);
    this.opts.diagnostics.delete(uri);
    this.sessionByUri.delete(key);
  }

  /** Force an immediate rescan (used by manual command). */
  async scanNow(doc: vscode.TextDocument): Promise<void> {
    return this.runScan(doc);
  }

  private schedule(doc: vscode.TextDocument): void {
    if (!this.opts.enabled()) return;
    if (!this.shouldScan(doc)) return;
    const key = doc.uri.toString();
    const existing = this.pending.get(key);
    if (existing) clearTimeout(existing.timer);
    const timer = setTimeout(() => {
      this.pending.delete(key);
      void this.runScan(doc).catch((err) => {
        // Surface errors via the diagnostic collection footer so the
        // user sees that scans aren't running, without spamming
        // notifications.
        const msg =
          err instanceof Error ? err.message : String(err);
        this.opts.diagnostics.set(doc.uri, [
          new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 0),
            `Praesidio scan failed: ${msg}`,
            vscode.DiagnosticSeverity.Information,
          ),
        ]);
      });
    }, this.opts.debounceMs());
    this.pending.set(key, { timer, version: doc.version });
  }

  private shouldScan(doc: vscode.TextDocument): boolean {
    if (doc.uri.scheme !== "file" && doc.uri.scheme !== "untitled") {
      return false;
    }
    if (doc.lineCount === 0) return false;
    return true;
  }

  private async runScan(doc: vscode.TextDocument): Promise<void> {
    const text = doc.getText();
    if (text.length === 0) {
      this.opts.diagnostics.delete(doc.uri);
      return;
    }

    const maxBytes = this.opts.maxBytes();
    const chunks = chunkDocument(text, maxBytes);
    const credential = await this.opts.getCredential();

    const key = doc.uri.toString();
    let sessionId = this.sessionByUri.get(key);
    if (!sessionId) {
      sessionId = `vscode:${key}`;
      this.sessionByUri.set(key, sessionId);
    }

    const diagnostics: vscode.Diagnostic[] = [];
    const allFindings: ScanFinding[] = [];
    for (const chunk of chunks) {
      const resp = await this.opts.client.scan(
        {
          text: chunk.text,
          client: "vscode",
          url: doc.uri.toString(),
          model: "praesidio-edge-scan",
          session_id: sessionId,
        },
        credential,
      );
      for (const f of resp.findings) {
        allFindings.push(f);
        const range = findingRange(doc, chunk.startOffset, f);
        const diag = new vscode.Diagnostic(
          range,
          `[Praesidio] ${f.label} (${f.detector}, conf ${f.confidence.toFixed(2)})`,
          this.opts.severity(),
        );
        diag.code = f.label;
        diag.source = "praesidio";
        diagnostics.push(diag);
      }
    }
    this.opts.diagnostics.set(doc.uri, diagnostics);
    this.opts.onScanComplete?.(doc.uri, allFindings);
  }
}

/**
 * Translate a `findings[].start/.end` (character offset within the
 * chunk) back to a `vscode.Range` in the original document.
 *
 * Exported for tests.
 */
export function findingRange(
  doc: vscode.TextDocument,
  chunkStartOffset: number,
  f: ScanFinding,
): vscode.Range {
  const start = chunkStartOffset + f.start;
  const end = chunkStartOffset + f.end;
  return new vscode.Range(doc.positionAt(start), doc.positionAt(end));
}
