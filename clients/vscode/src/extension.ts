/**
 * Praesidio VS Code extension — activation entry point.
 *
 * Wires together:
 *   - settings reader + change subscriber
 *   - SecretStorage-backed auth
 *   - gateway HTTP client
 *   - status bar
 *   - decisions tree view
 *   - per-document scanner + diagnostics
 *   - code-action provider (quick-fix "Tokenise")
 *   - all five user-facing commands
 *   - the proxy controller (auto-start if configured)
 */

import * as vscode from "vscode";

import { AuthManager } from "./auth.js";
import { registerOpenAudit } from "./commands/openAudit.js";
import { registerScanSelection } from "./commands/scanSelection.js";
import { registerSignIn } from "./commands/signIn.js";
import { registerToggleProxy } from "./commands/toggleProxy.js";
import { registerTokeniseSelection } from "./commands/tokeniseSelection.js";
import { TokeniseCodeActionProvider } from "./codeActions/tokeniseProvider.js";
import { DecisionStore, DecisionsTreeProvider } from "./decisionsView.js";
import { createPraesidioDiagnostics } from "./diagnostics/provider.js";
import { DocumentScanner } from "./diagnostics/scanner.js";
import { GatewayClient } from "./gateway.js";
import { ProxyController } from "./proxy/controller.js";
import {
  onSettingsChanged,
  readSettings,
  toVscodeSeverity,
} from "./settings.js";
import { PraesidioStatusBar } from "./statusbar.js";

export function activate(context: vscode.ExtensionContext): void {
  let settings = readSettings();

  const auth = new AuthManager(context.secrets);
  const client = new GatewayClient({ baseUrl: settings.gateway.url });
  const store = new DecisionStore();
  context.subscriptions.push(store);

  // -- tree view -----------------------------------------------------------
  const treeProvider = new DecisionsTreeProvider(store);
  context.subscriptions.push(treeProvider);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      "praesidio.decisions",
      treeProvider,
    ),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("praesidio.refreshDecisions", () => {
      // Tree refreshes from store events; nothing else to do.
    }),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("praesidio.clearDecisions", () => {
      store.clear();
    }),
  );

  // -- status bar ----------------------------------------------------------
  const statusBar = new PraesidioStatusBar(store, settings);
  context.subscriptions.push(statusBar);
  void auth.hasCredential().then((b) => statusBar.setSignedIn(b));

  // -- diagnostics ---------------------------------------------------------
  const diagnostics = createPraesidioDiagnostics();
  context.subscriptions.push(diagnostics);
  const scanner = new DocumentScanner({
    client,
    diagnostics,
    getCredential: () => auth.current(settings.gateway.tenantId || null),
    severity: () => toVscodeSeverity(settings.diagnostics.severity),
    debounceMs: () => settings.diagnostics.debounceMs,
    maxBytes: () => settings.diagnostics.maxBytes,
    enabled: () => settings.diagnostics.enabled,
  });
  context.subscriptions.push(scanner);

  // -- code action ---------------------------------------------------------
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      "*",
      new TokeniseCodeActionProvider(),
      {
        providedCodeActionKinds:
          TokeniseCodeActionProvider.providedCodeActionKinds,
      },
    ),
  );

  // -- proxy ---------------------------------------------------------------
  const proxy = new ProxyController();
  context.subscriptions.push(proxy);
  context.subscriptions.push(
    proxy.onStateChange((s) => statusBar.setProxyState(s)),
  );

  // -- commands ------------------------------------------------------------
  context.subscriptions.push(
    registerScanSelection({
      client,
      store,
      getCredential: () => auth.current(settings.gateway.tenantId || null),
    }),
    registerTokeniseSelection({
      client,
      store,
      getCredential: () => auth.current(settings.gateway.tenantId || null),
    }),
    registerToggleProxy({
      controller: proxy,
      auth,
      getSettings: () => settings,
    }),
    ...registerSignIn({
      auth,
      getSettings: () => settings,
      onChanged: () => {
        void auth.hasCredential().then((b) => statusBar.setSignedIn(b));
      },
    }),
    registerOpenAudit({
      auth,
      getSettings: () => settings,
    }),
  );

  // -- settings change -----------------------------------------------------
  context.subscriptions.push(
    onSettingsChanged((next) => {
      const baseUrlChanged = next.gateway.url !== settings.gateway.url;
      settings = next;
      statusBar.setSettings(next);
      if (baseUrlChanged) {
        // GatewayClient is constructed once and read-only — but our
        // closures read `settings` so the URL change takes effect on
        // the next call.
        Object.defineProperty(client, "baseUrl", {
          value: next.gateway.url.replace(/\/+$/, ""),
          configurable: true,
        });
      }
      // If diagnostics were just disabled, clear the collection.
      if (!next.diagnostics.enabled) {
        diagnostics.clear();
      }
    }),
  );

  // -- auto-start proxy ----------------------------------------------------
  if (settings.proxy.autoStart) {
    void auth.current(settings.gateway.tenantId || null).then((cred) => {
      void proxy
        .start({
          binaryPath: settings.proxy.binaryPath,
          gatewayUrl: settings.gateway.url,
          port: settings.proxy.port,
          apiKey: cred.apiKey ?? null,
          bearerToken: cred.bearerToken ?? null,
        })
        .catch((err) => {
          void vscode.window.showWarningMessage(
            `Praesidio: proxy auto-start failed — ${(err as Error).message}`,
          );
        });
    });
  }
}

export function deactivate(): void {
  // Disposables registered in `activate` are flushed by VS Code itself;
  // `ProxyController.dispose` stops the child process cleanly.
}
