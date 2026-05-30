/**
 * CodeActionProvider that offers "Section: Tokenise" as a quick-fix
 * for any diagnostic emitted by the document scanner.
 *
 * When invoked, the action runs `section.tokeniseSelection` with the
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
    const sectionDiags = context.diagnostics.filter(
      (d) => d.source === "section",
    );
    if (sectionDiags.length === 0) return [];

    const actions: vscode.CodeAction[] = [];
    for (const diag of sectionDiags) {
      const a = new vscode.CodeAction(
        `Section: Tokenise ${diag.code ?? "sensitive data"}`,
        vscode.CodeActionKind.QuickFix,
      );
      a.diagnostics = [diag];
      a.isPreferred = sectionDiags.length === 1;
      a.command = {
        command: "section.tokeniseSelection",
        title: "Section: Tokenise",
        arguments: [
          { uri: document.uri.toString(), range: serialiseRange(diag.range) },
        ],
      };
      actions.push(a);
    }
    // Also offer a single "tokenise all findings in this range" command.
    if (sectionDiags.length > 1) {
      const all = new vscode.CodeAction(
        `Section: Tokenise ${sectionDiags.length} findings`,
        vscode.CodeActionKind.QuickFix,
      );
      all.diagnostics = sectionDiags;
      all.command = {
        command: "section.tokeniseSelection",
        title: "Section: Tokenise",
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
