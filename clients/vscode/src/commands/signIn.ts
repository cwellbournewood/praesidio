/**
 * "Praesidio: Sign In" and "Praesidio: Sign Out".
 *
 * Sign-in offers two flows:
 *   1. API key — prompts for the key, stores in SecretStorage.
 *   2. OIDC device code — runs `AuthManager.signInWithDeviceCode`.
 *
 * The choice is presented as a quick-pick.
 */

import * as vscode from "vscode";

import type { AuthManager } from "../auth.js";
import type { PraesidioSettings } from "../settings.js";

export interface SignInDeps {
  auth: AuthManager;
  getSettings: () => PraesidioSettings;
  onChanged?: () => void;
}

export function registerSignIn(deps: SignInDeps): vscode.Disposable[] {
  const signIn = vscode.commands.registerCommand(
    "praesidio.signIn",
    async () => {
      const pick = await vscode.window.showQuickPick(
        [
          {
            id: "apikey",
            label: "API Key",
            description: "Paste an X-API-Key value (recommended for dev)",
          },
          {
            id: "oidc",
            label: "OIDC Device Code",
            description: "Sign in via your IdP in the browser",
          },
        ],
        { title: "Praesidio: choose auth method" },
      );
      if (!pick) return;
      if (pick.id === "apikey") {
        const key = await vscode.window.showInputBox({
          prompt: "Praesidio API key (X-API-Key)",
          password: true,
          ignoreFocusOut: true,
          placeHolder: "praes_...",
          validateInput: (v) => (v.trim().length === 0 ? "Required." : null),
        });
        if (!key) return;
        await deps.auth.setApiKey(key.trim());
        void vscode.window.showInformationMessage(
          "Praesidio: API key stored.",
        );
        deps.onChanged?.();
        return;
      }
      // OIDC
      const s = deps.getSettings();
      const device =
        s.oidc.deviceCodeEndpoint ||
        joinUrl(s.gateway.url, "/oidc/device_authorization");
      const tokenUrl =
        s.oidc.tokenEndpoint || joinUrl(s.gateway.url, "/oidc/token");
      try {
        const ok = await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Praesidio: signing in…",
            cancellable: true,
          },
          (progress, token) =>
            deps.auth.signInWithDeviceCode({
              deviceCodeEndpoint: device,
              tokenEndpoint: tokenUrl,
              clientId: s.oidc.clientId,
              scopes: s.oidc.scopes,
              progress,
              token,
            }),
        );
        if (ok) {
          void vscode.window.showInformationMessage(
            "Praesidio: signed in.",
          );
          deps.onChanged?.();
        }
      } catch (err) {
        void vscode.window.showErrorMessage(
          `Praesidio sign-in failed: ${(err as Error).message}`,
        );
      }
    },
  );

  const signOut = vscode.commands.registerCommand(
    "praesidio.signOut",
    async () => {
      await deps.auth.signOut();
      void vscode.window.showInformationMessage(
        "Praesidio: signed out.",
      );
      deps.onChanged?.();
    },
  );

  return [signIn, signOut];
}

function joinUrl(base: string, path: string): string {
  return base.replace(/\/+$/, "") + (path.startsWith("/") ? path : `/${path}`);
}
