/**
 * "Section: Tokenise Selection" — companion to scan-selection.
 *
 * Two entry-shapes:
 *  - No args: take editor selection, scan, and if action == "mask"
 *    replace silently.
 *  - With `{ uri, range }`: target a specific range (used by the
 *    `tokeniseProvider` quick-fix from diagnostics).
 *
 * Always non-destructive on block — surfaces the same modal as
 * scan-selection.
 */

import * as vscode from "vscode";

import type { Credential, GatewayClient } from "../gateway.js";
import type { DecisionStore } from "../decisionsView.js";
import type { DecisionRecord } from "../lib/types.js";

export interface TokeniseSelectionDeps {
  client: GatewayClient;
  store: DecisionStore;
  getCredential: () => Promise<Credential>;
}

export interface TokeniseArgs {
  uri?: string;
  range?: [number, number, number, number];
}

export function registerTokeniseSelection(
  deps: TokeniseSelectionDeps,
): vscode.Disposable {
  return vscode.commands.registerCommand(
    "section.tokeniseSelection",
    async (args?: TokeniseArgs) => {
      const target = await resolveTarget(args);
      if (!target) {
        void vscode.window.showWarningMessage(
          "Section: no editor / range available.",
        );
        return;
      }
      const { editor, range } = target;
      const text = editor.document.getText(range);
      if (!text.trim()) {
        void vscode.window.showWarningMessage(
          "Section: selection is empty.",
        );
        return;
      }
      const cred = await deps.getCredential();
      let resp;
      try {
        resp = await deps.client.scan(
          {
            text,
            client: "vscode",
            url: editor.document.uri.toString(),
            model: "section-edge-tokenise",
            session_id: `vscode-tokenise:${editor.document.uri.toString()}`,
          },
          cred,
        );
      } catch (err) {
        void vscode.window.showErrorMessage(
          `Section tokenise failed: ${(err as Error).message}`,
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
        excerpt: text.replace(/\s+/g, " ").slice(0, 200),
      };
      deps.store.push(record);

      if (resp.action === "block") {
        await vscode.window.showErrorMessage(
          `Section blocked: ${resp.reason ?? "policy violation"}`,
          { modal: true },
        );
        return;
      }
      if (resp.action === "allow") {
        void vscode.window.setStatusBarMessage(
          "$(check) Section: nothing to tokenise.",
          3000,
        );
        return;
      }
      const sanitised = resp.sanitised ?? text;
      await editor.edit((eb) => {
        eb.replace(range, sanitised);
      });
      void vscode.window.setStatusBarMessage(
        `$(shield) Section: tokenised ${resp.transforms.length} value(s).`,
        4000,
      );
    },
  );
}

async function resolveTarget(
  args?: TokeniseArgs,
): Promise<{ editor: vscode.TextEditor; range: vscode.Range } | null> {
  if (args?.uri && args.range && args.range.length === 4) {
    const uri = vscode.Uri.parse(args.uri);
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc, {
      preserveFocus: false,
      preview: false,
    });
    const [sl, sc, el, ec] = args.range as [number, number, number, number];
    return { editor, range: new vscode.Range(sl, sc, el, ec) };
  }
  const editor = vscode.window.activeTextEditor;
  if (!editor) return null;
  const sel = editor.selection;
  if (sel.isEmpty) {
    return {
      editor,
      range: new vscode.Range(
        editor.document.positionAt(0),
        editor.document.positionAt(editor.document.getText().length),
      ),
    };
  }
  return { editor, range: new vscode.Range(sel.start, sel.end) };
}
