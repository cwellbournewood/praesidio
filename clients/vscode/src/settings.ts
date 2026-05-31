/**
 * Settings reader for the Section VS Code extension.
 *
 * Wraps `vscode.workspace.getConfiguration("section")` with a typed
 * facade. All callers should go through this module so test mocks can
 * stub a single boundary.
 */

import * as vscode from "vscode";

export interface SectionSettings {
  gateway: {
    url: string;
    apiKeyEcho: string;
    tenantId: string;
  };
  diagnostics: {
    enabled: boolean;
    debounceMs: number;
    severity: "error" | "warning" | "information" | "hint";
    maxBytes: number;
  };
  proxy: {
    autoStart: boolean;
    binaryPath: string;
    port: number;
  };
  statusBar: {
    enabled: boolean;
  };
  oidc: {
    deviceCodeEndpoint: string;
    tokenEndpoint: string;
    clientId: string;
    scopes: string;
  };
}

export function readSettings(): SectionSettings {
  const c = vscode.workspace.getConfiguration("section");
  return {
    gateway: {
      url: c.get<string>("gateway.url", "http://localhost:8080").trim(),
      apiKeyEcho: c.get<string>("gateway.apiKey", ""),
      tenantId: c.get<string>("gateway.tenantId", "").trim(),
    },
    diagnostics: {
      enabled: c.get<boolean>("diagnostics.enabled", true),
      debounceMs: c.get<number>("diagnostics.debounceMs", 800),
      severity: c.get<"error" | "warning" | "information" | "hint">(
        "diagnostics.severity",
        "warning",
      ),
      maxBytes: c.get<number>("diagnostics.maxBytes", 262_144),
    },
    proxy: {
      autoStart: c.get<boolean>("proxy.autoStart", false),
      binaryPath: c.get<string>("proxy.binaryPath", "section-edge-proxy"),
      port: c.get<number>("proxy.port", 8889),
    },
    statusBar: {
      enabled: c.get<boolean>("statusBar.enabled", true),
    },
    oidc: {
      deviceCodeEndpoint: c.get<string>("oidc.deviceCodeEndpoint", "").trim(),
      tokenEndpoint: c.get<string>("oidc.tokenEndpoint", "").trim(),
      clientId: c.get<string>("oidc.clientId", "section-vscode"),
      scopes: c.get<string>("oidc.scopes", "openid profile section.edge"),
    },
  };
}

export function toVscodeSeverity(
  s: "error" | "warning" | "information" | "hint",
): vscode.DiagnosticSeverity {
  switch (s) {
    case "error":
      return vscode.DiagnosticSeverity.Error;
    case "warning":
      return vscode.DiagnosticSeverity.Warning;
    case "information":
      return vscode.DiagnosticSeverity.Information;
    case "hint":
      return vscode.DiagnosticSeverity.Hint;
  }
}

/**
 * Subscribe to configuration changes; invokes `cb` whenever any
 * `section.*` setting changes. Returns the disposable.
 */
export function onSettingsChanged(
  cb: (next: SectionSettings) => void,
): vscode.Disposable {
  return vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration("section")) {
      cb(readSettings());
    }
  });
}
