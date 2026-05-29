/**
 * Status-bar widget for the Praesidio extension.
 *
 * Bottom-left "$(shield) Praesidio" pill. Tooltip shows gateway URL,
 * last decision, and proxy state. Clicking the pill opens a quick-pick
 * with sign-in / toggle-proxy / scan-selection / open-audit.
 */

import * as vscode from "vscode";

import type { DecisionStore } from "./decisionsView.js";
import type { PraesidioSettings } from "./settings.js";
import type { ProxyState } from "./lib/types.js";

export class PraesidioStatusBar {
  private readonly item: vscode.StatusBarItem;
  private readonly subs: vscode.Disposable[] = [];
  private proxyState: ProxyState = "stopped";
  private signedIn = false;

  constructor(
    private readonly store: DecisionStore,
    private settings: PraesidioSettings,
  ) {
    this.item = vscode.window.createStatusBarItem(
      "praesidio.statusBar",
      vscode.StatusBarAlignment.Left,
      0,
    );
    this.item.name = "Praesidio";
    this.item.command = "praesidio.statusBar.menu";
    this.subs.push(this.item);
    this.subs.push(
      this.store.onDidChange(() => this.render()),
    );
    this.subs.push(
      vscode.commands.registerCommand(
        "praesidio.statusBar.menu",
        () => this.showMenu(),
      ),
    );
    this.render();
  }

  setSettings(s: PraesidioSettings): void {
    this.settings = s;
    this.render();
  }

  setProxyState(s: ProxyState): void {
    this.proxyState = s;
    this.render();
  }

  setSignedIn(v: boolean): void {
    this.signedIn = v;
    this.render();
  }

  /** Force a one-shot tooltip refresh (used after sign-in / sign-out). */
  refresh(): void {
    this.render();
  }

  dispose(): void {
    for (const s of this.subs) s.dispose();
  }

  private render(): void {
    if (!this.settings.statusBar.enabled) {
      this.item.hide();
      return;
    }
    const last = this.store.last();
    const lastTag = last ? ` • ${last.action}` : "";
    this.item.text = `$(shield) Praesidio${lastTag}`;

    const md = new vscode.MarkdownString();
    md.isTrusted = false;
    md.appendMarkdown(`**Praesidio**\n\n`);
    md.appendMarkdown(`- gateway: \`${this.settings.gateway.url}\`\n`);
    md.appendMarkdown(
      `- signed in: ${this.signedIn ? "yes" : "no"}\n`,
    );
    md.appendMarkdown(`- proxy: ${this.proxyState}\n`);
    if (last) {
      md.appendMarkdown(
        `- last decision: \`${last.action}\` at ${last.occurredAt}\n`,
      );
      if (last.reason) md.appendMarkdown(`- reason: ${last.reason}\n`);
    } else {
      md.appendMarkdown(`- last decision: none yet\n`);
    }
    md.appendMarkdown("\nClick for quick actions.");
    this.item.tooltip = md;

    // Background color hints when blocked / error.
    if (last?.action === "block") {
      this.item.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.errorBackground",
      );
    } else if (this.proxyState === "error") {
      this.item.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.warningBackground",
      );
    } else {
      this.item.backgroundColor = undefined;
    }
    this.item.show();
  }

  private async showMenu(): Promise<void> {
    const items: (vscode.QuickPickItem & { id: string })[] = [
      {
        id: "scan",
        label: "$(shield) Scan Selection",
        description: "Run /v1/scan on the current editor selection",
      },
      {
        id: this.signedIn ? "signout" : "signin",
        label: this.signedIn
          ? "$(sign-out) Sign Out"
          : "$(sign-in) Sign In",
        description: this.signedIn
          ? "Clear stored credentials"
          : "OIDC device-code flow",
      },
      {
        id: "proxy",
        label:
          this.proxyState === "running"
            ? "$(circle-slash) Stop Local Proxy"
            : "$(play) Start Local Proxy",
        description: `proxy state: ${this.proxyState}`,
      },
      {
        id: "audit",
        label: "$(book) Open Audit Trail",
        description: "Open /admin/events on the gateway",
      },
    ];
    const pick = await vscode.window.showQuickPick(items, {
      title: "Praesidio",
      placeHolder: "What would you like to do?",
    });
    if (!pick) return;
    switch (pick.id) {
      case "scan":
        await vscode.commands.executeCommand("praesidio.scanSelection");
        return;
      case "signin":
        await vscode.commands.executeCommand("praesidio.signIn");
        return;
      case "signout":
        await vscode.commands.executeCommand("praesidio.signOut");
        return;
      case "proxy":
        await vscode.commands.executeCommand("praesidio.toggleProxy");
        return;
      case "audit":
        await vscode.commands.executeCommand("praesidio.openAudit");
        return;
    }
  }
}
