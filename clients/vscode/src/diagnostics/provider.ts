/**
 * Owns the `vscode.DiagnosticCollection` instance.
 *
 * Kept in a separate module so multiple producers (the document
 * scanner; the manual scan-selection command) can write to the same
 * collection without each module re-creating it.
 */

import * as vscode from "vscode";

export function createSectionDiagnostics(): vscode.DiagnosticCollection {
  return vscode.languages.createDiagnosticCollection("section");
}
