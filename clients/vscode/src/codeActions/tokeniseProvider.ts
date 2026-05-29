/**
 * CodeActionProvider that offers "Praesidio: Tokenise" as a quick-fix
 * for any diagnostic emitted by the document scanner.
 *
 * When invoked, the action runs `praesidio.tokeniseSelection` with the
 * diagnostic's range. The actual /v1/scan + replace logic lives in
 * `commands/tokeniseSelection.ts`.
 */

import * as vscode from "vscode";

export class TokeniseCodeActionProvider
  implements vscode.CodeActionProvider
{
  static readonly providedCodeActionKinds = [
    vscode.CodeActionKind.QuickFix,
  ];

  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range,
    context: vscode.CodeActionContext,
  ): vscode.CodeAction[] {
    const praesidioDiags = context.diagnostics.filter(
      (d) => d.source === "praesidio",
    );
    if (praesidioDiags.length === 0) return [];

    const actions: vscode.CodeAction[] = [];
    for (const diag of praesidioDiags) {
      const a = new vscode.CodeAction(
        `Praesidio: Tokenise ${diag.code ?? "sensitive data"}`,
        vscode.CodeActionKind.QuickFix,
      );
      a.diagnostics = [diag];
      a.isPreferred = praesidioDiags.length === 1;
      a.command = {
        command: "praesidio.tokeniseSelection",
        title: "Praesidio: Tokenise",
        arguments: [
          { uri: document.uri.toString(), range: serialiseRange(diag.range) },
        ],
      };
      actions.push(a);
    }
    // Also offer a single "tokenise all findings in this range" command.
    if (praesidioDiags.length > 1) {
      const all = new vscode.CodeAction(
        `Praesidio: Tokenise ${praesidioDiags.length} findings`,
        vscode.CodeActionKind.QuickFix,
      );
      all.diagnostics = praesidioDiags;
      all.command = {
        command: "praesidio.tokeniseSelection",
        title: "Praesidio: Tokenise",
        arguments: [
          { uri: document.uri.toString(), range: serialiseRange(range) },
        ],
      };
      actions.push(all);
    }
    return actions;
  }
}

function serialiseRange(r: vscode.Range): [number, number, number, number] {
  return [r.start.line, r.start.character, r.end.line, r.end.character];
}
