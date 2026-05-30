/**
 * "Section: Open Audit Trail" — opens the gateway's /admin/events
 * route in the user's default browser, filtered to the current tenant
 * if known.
 */

import * as vscode from "vscode";

import type { AuthManager } from "../auth.js";
import type { SectionSettings } from "../settings.js";

export interface OpenAuditDeps {
  auth: AuthManager;
  getSettings: () => SectionSettings;
}

export function registerOpenAudit(deps: OpenAuditDeps): vscode.Disposable {
  return vscode.commands.registerCommand(
    "section.openAudit",
    async () => {
      const s = deps.getSettings();
      const cred = await deps.auth.current(s.gateway.tenantId || null);
      const url = new URL(
        s.gateway.url.replace(/\/+$/, "") + "/admin/events",
      );
      if (cred.tenantId) {
        url.searchParams.set("tenant_id", cred.tenantId);
      }
      url.searchParams.set("limit", "50");
      await vscode.env.openExternal(vscode.Uri.parse(url.toString()));
    },
  );
}
