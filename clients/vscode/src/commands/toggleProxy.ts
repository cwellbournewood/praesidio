/**
 * "Section: Toggle Local Proxy" — start or stop the
 * section-edge-proxy child process.
 */

import * as vscode from "vscode";

import type { ProxyController } from "../proxy/controller.js";
import type { AuthManager } from "../auth.js";
import type { SectionSettings } from "../settings.js";

export interface ToggleProxyDeps {
  controller: ProxyController;
  auth: AuthManager;
  getSettings: () => SectionSettings;
}

export function registerToggleProxy(
  deps: ToggleProxyDeps,
): vscode.Disposable {
  return vscode.commands.registerCommand(
    "section.toggleProxy",
    async () => {
      const s = deps.getSettings();
      if (
        deps.controller.state === "running" ||
        deps.controller.state === "starting"
      ) {
        await deps.controller.stop();
        void vscode.window.showInformationMessage(
          "Section: local proxy stopped.",
        );
        return;
      }
      const cred = await deps.auth.current(s.gateway.tenantId || null);
      try {
        await deps.controller.start({
          binaryPath: s.proxy.binaryPath,
          gatewayUrl: s.gateway.url,
          port: s.proxy.port,
          apiKey: cred.apiKey ?? null,
          bearerToken: cred.bearerToken ?? null,
        });
        void vscode.window.showInformationMessage(
          `Section: local proxy started on port ${s.proxy.port}. Set HTTPS_PROXY=http://localhost:${s.proxy.port}.`,
        );
      } catch (err) {
        void vscode.window.showErrorMessage(
          `Section: failed to start proxy — ${(err as Error).message}. Is section-edge-proxy on PATH?`,
        );
      }
    },
  );
}
