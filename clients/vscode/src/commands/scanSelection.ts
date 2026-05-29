/**
 * "Praesidio: Scan Selection" command.
 *
 * Behaviour:
 *  1. Grab the current editor selection (fall back to the whole document).
 *  2. POST to /v1/scan.
 *  3. If action == "mask": open a side-by-side diff between the
 *     original selection and the returned `sanitised` text, with a
 *     modal "Replace" button.
 *  4. If action == "block": modal error with `reason` / `severity`.
 *  5. If action == "allow": ephemeral status-bar tick.
 */

import * as vscode from "vscode";

import type { Credential, GatewayClient } from "../gateway.js";
import type { DecisionStore } from "../decisionsView.js";
import type { DecisionRecord } from "../lib/types.js";

export interface ScanSelectionDeps {
  client: GatewayClient;
  store: DecisionStore;
  getCredential: () => Promise<Credential>;
}

export function registerScanSelection(
  deps: ScanSelectionDeps,
): vscode.Disposable {
  return vscode.commands.registerCommand(
    "praesidio.scanSelection",
    async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        void vscode.window.showWarningMessage(
          "Praesidio: no active editor.",
        );
        return;
      }
      const sel = editor.selection;
      const range = sel.isEmpty
        ? new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(editor.document.getText().length),
          )
        : new vscode.Range(sel.start, sel.end);
      const text = editor.document.getText(range);
      if (!text.trim()) {
        void vscode.window.showWarningMessage(
          "Praesidio: selection is empty.",
        );
        return;
      }

      const cred = await deps.getCredential();
      let resp;
      try {
        resp = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Praesidio: scanning selection…",
            cancellable: false,
          },
          () =>
            deps.client.scan(
              {
                text,
                client: "vscode",
                url: editor.document.uri.toString(),
                model: "praesidio-edge-scan-selection",
                session_id: `vscode-sel:${editor.document.uri.toString()}`,
              },
              cred,
            ),
        );
      } catch (err) {
        void vscode.window.showErrorMessage(
          `Praesidio scan failed: ${(err as Error).message}`,
        );
        return;
      }

      const record: DecisionRecord = {
        request_id: resp.request_id,
        action: resp.action,
        reason: resp.reason ?? resp.decision.reason ?? null,
        severity: resp.severity ?? resp.decision.severity ?? null,
        uri: editor.document.uri.toString(),
        occurredAt: new Date().toISOString(),
        findingCount: resp.findings.length,
        transformCount: resp.transforms.length,
        excerpt: excerptFor(text),
      };
      deps.store.push(record);

      if (resp.action === "block") {
        await vscode.window.showErrorMessage(
          `Praesidio blocked the selection: ${resp.reason ?? "policy violation"} (severity: ${resp.severity ?? "unknown"})`,
          { modal: true },
        );
        return;
      }

      if (resp.action === "allow") {
        void vscode.window.setStatusBarMessage(
          "$(check) Praesidio: no sensitive data found.",
          4000,
        );
        return;
      }

      // action === "mask"
      const sanitised = resp.sanitised ?? text;
      const pick = await showMaskPreview(text, sanitised, resp.transforms.length);
      if (pick === "replace") {
        await editor.edit((eb) => {
          eb.replace(range, sanitised);
        });
        void vscode.window.showInformationMessage(
          `Praesidio: replaced ${resp.transforms.length} sensitive value(s).`,
        );
      }
    },
  );
}

function excerptFor(text: string): string {
  const single = text.replace(/\s+/g, " ").trim();
  return single.length > 200 ? single.slice(0, 197) + "…" : single;
}

async function showMaskPreview(
  original: string,
  sanitised: string,
  transformCount: number,
): Promise<"replace" | "cancel"> {
  const left = await vscode.workspace.openTextDocument({
    content: original,
    language: "plaintext",
  });
  const right = await vscode.workspace.openTextDocument({
    content: sanitised,
    language: "plaintext",
  });
  await vscode.commands.executeCommand(
    "vscode.diff",
    left.uri,
    right.uri,
    `Praesidio: original ↔ sanitised (${transformCount} transform${transformCount === 1 ? "" : "s"})`,
    { preview: true, preserveFocus: false },
  );
  const decision = await vscode.window.showInformationMessage(
    `Praesidio found ${transformCount} sensitive value(s). Replace the selection with the sanitised text?`,
    { modal: true },
    "Replace",
    "Cancel",
  );
  return decision === "Replace" ? "replace" : "cancel";
}
