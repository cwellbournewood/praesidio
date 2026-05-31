/**
 * The "Recent Decisions" tree view shown in the Section activity-bar
 * container. Backed by an in-memory ring buffer of the last N decisions
 * the user has seen (~50). Never persisted.
 */

import * as vscode from "vscode";

import type { DecisionRecord, ScanAction } from "./lib/types.js";

const MAX_DECISIONS = 50;

export class DecisionStore {
  private items: DecisionRecord[] = [];
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChange = this.emitter.event;

  push(record: DecisionRecord): void {
    this.items.unshift(record);
    if (this.items.length > MAX_DECISIONS) {
      this.items.length = MAX_DECISIONS;
    }
    this.emitter.fire();
  }

  clear(): void {
    this.items = [];
    this.emitter.fire();
  }

  list(): readonly DecisionRecord[] {
    return this.items;
  }

  last(): DecisionRecord | undefined {
    return this.items[0];
  }

  dispose(): void {
    this.emitter.dispose();
  }
}

export class DecisionsTreeProvider
  implements vscode.TreeDataProvider<DecisionRecord>
{
  private readonly emitter = new vscode.EventEmitter<DecisionRecord | undefined | void>();
  readonly onDidChangeTreeData = this.emitter.event;
  private storeSub: vscode.Disposable;

  constructor(private readonly store: DecisionStore) {
    this.storeSub = this.store.onDidChange(() => this.emitter.fire());
  }

  getTreeItem(element: DecisionRecord): vscode.TreeItem {
    const item = new vscode.TreeItem(
      titleFor(element),
      vscode.TreeItemCollapsibleState.None,
    );
    item.description = element.occurredAt;
    item.tooltip = tooltipFor(element);
    item.iconPath = new vscode.ThemeIcon(iconFor(element.action));
    item.contextValue = `section.decision.${element.action}`;
    return item;
  }

  getChildren(element?: DecisionRecord): DecisionRecord[] {
    if (element) return [];
    return Array.from(this.store.list());
  }

  dispose(): void {
    this.storeSub.dispose();
    this.emitter.dispose();
  }
}

function titleFor(d: DecisionRecord): string {
  const prefix = d.action.toUpperCase();
  if (d.excerpt) {
    return `${prefix} • ${truncate(d.excerpt, 64)}`;
  }
  return prefix;
}

function tooltipFor(d: DecisionRecord): vscode.MarkdownString {
  const md = new vscode.MarkdownString();
  md.appendMarkdown(`**Section decision** — \`${d.action}\`\n\n`);
  md.appendMarkdown(`- request: \`${d.request_id}\`\n`);
  md.appendMarkdown(`- at: ${d.occurredAt}\n`);
  if (d.uri) md.appendMarkdown(`- file: \`${d.uri}\`\n`);
  if (d.findingCount) md.appendMarkdown(`- findings: ${d.findingCount}\n`);
  if (d.transformCount) {
    md.appendMarkdown(`- transforms: ${d.transformCount}\n`);
  }
  if (d.reason) md.appendMarkdown(`- reason: ${d.reason}\n`);
  if (d.severity) md.appendMarkdown(`- severity: ${d.severity}\n`);
  if (d.excerpt) {
    md.appendMarkdown("\n---\n");
    md.appendCodeblock(d.excerpt, "text");
  }
  return md;
}

function iconFor(a: ScanAction): string {
  switch (a) {
    case "allow":
      return "pass";
    case "mask":
      return "shield";
    case "block":
      return "error";
  }
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}
