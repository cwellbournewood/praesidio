/**
 * "Praesidio: Toggle Local Proxy" — start or stop the
 * praesidio-edge-proxy child process.
 */

import * as vscode from "vscode";

import type { ProxyController } from "../proxy/controller.js";
import type { AuthManager } from "../auth.js";
import type { PraesidioSettings } from "../settings.js";

export interface ToggleProxyDeps {
  controller: ProxyController;
  auth: AuthManager;
  getSettings: () => PraesidioSettings;
}

export function registerToggleProxy(
  deps: ToggleProxyDeps,
): vscode.Disposable {
  return vscode.commands.registerCommand(
    "praesidio.toggleProxy",
    async () => {
      const s = deps.getSettings();
      if (
        deps.controller.state === "running" ||
        deps.controller.state === "starting"
      ) {
        await deps.controller.stop();
        void vscode.window.showInformationMessage(
          "Praesidio: local proxy stopped.",
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
          `Praesidio: local proxy started on port ${s.proxy.port}. Set HTTPS_PROXY=http://localhost:${s.proxy.port}.`,
        );
      } catch (err) {
        void vscode.window.showErrorMessage(
          `Praesidio: failed to start proxy — ${(err as Error).message}. Is praesidio-edge-proxy on PATH?`,
        );
      }
    },
  );
}
