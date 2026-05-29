/**
 * Minimal `vscode` API mock for unit tests.
 *
 * The real module is only available when running under @vscode/test-electron.
 * For unit tests we need a tiny shim that satisfies the surface our
 * source modules import. We deliberately register this shim under the
 * literal module name "vscode" via Node's CommonJS cache hack so
 * `import * as vscode from "vscode"` returns this stub.
 *
 * To use:
 *
 *   import "./vscode-mock.ts";  // side-effect: installs the stub
 *   import { DecisionStore } from "../src/decisionsView.js";
 *
 * Each test file should import this BEFORE any src module.
 */

import Module from "node:module";

type Listener<T> = (e: T) => void;

class EventEmitter<T> {
  private listeners: Listener<T>[] = [];
  readonly event = (cb: Listener<T>): { dispose(): void } => {
    this.listeners.push(cb);
    return {
      dispose: (): void => {
        this.listeners = this.listeners.filter((l) => l !== cb);
      },
    };
  };
  fire(e: T): void {
    for (const cb of this.listeners) cb(e);
  }
  dispose(): void {
    this.listeners = [];
  }
}

class Position {
  constructor(
    public readonly line: number,
    public readonly character: number,
  ) {}
}

class Range {
  public readonly start: Position;
  public readonly end: Position;
  constructor(
    a: Position | number,
    b: Position | number,
    c?: number,
    d?: number,
  ) {
    if (a instanceof Position && b instanceof Position) {
      this.start = a;
      this.end = b;
    } else {
      this.start = new Position(a as number, b as number);
      this.end = new Position(c as number, d as number);
    }
  }
}

enum DiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

class Diagnostic {
  source?: string;
  code?: string | number;
  constructor(
    public range: Range,
    public message: string,
    public severity: DiagnosticSeverity = DiagnosticSeverity.Warning,
  ) {}
}

class Uri {
  static parse(s: string): Uri {
    return new Uri(s);
  }
  static file(s: string): Uri {
    return new Uri(`file://${s}`);
  }
  private constructor(public readonly s: string) {}
  toString(): string {
    return this.s;
  }
  get scheme(): string {
    const idx = this.s.indexOf(":");
    return idx === -1 ? "" : this.s.slice(0, idx);
  }
}

class MarkdownString {
  isTrusted = false;
  value = "";
  appendMarkdown(s: string): this {
    this.value += s;
    return this;
  }
  appendCodeblock(s: string, _lang: string): this {
    this.value += `\n\`\`\`\n${s}\n\`\`\``;
    return this;
  }
}

class ThemeIcon {
  constructor(public readonly id: string) {}
}

class ThemeColor {
  constructor(public readonly id: string) {}
}

class TreeItem {
  description?: string;
  tooltip?: MarkdownString | string;
  iconPath?: ThemeIcon;
  contextValue?: string;
  constructor(
    public readonly label: string,
    public readonly collapsibleState: number,
  ) {}
}

enum TreeItemCollapsibleState {
  None = 0,
  Collapsed = 1,
  Expanded = 2,
}

enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

class CodeAction {
  diagnostics?: Diagnostic[];
  command?: { command: string; title: string; arguments?: unknown[] };
  isPreferred = false;
  constructor(public title: string, public kind: { value: string }) {}
}

const CodeActionKind = {
  QuickFix: { value: "quickfix" },
};

enum DiagnosticTag {
  Unnecessary = 1,
  Deprecated = 2,
}

class CancellationTokenSource {
  readonly token = { isCancellationRequested: false };
  cancel(): void {
    (this.token as { isCancellationRequested: boolean }).isCancellationRequested = true;
  }
  dispose(): void {}
}

// ---- workspace + window stubs ------------------------------------------

interface StubTextDocument {
  uri: Uri;
  version: number;
  lineCount: number;
  getText(): string;
  getText(range: Range): string;
  positionAt(o: number): Position;
}

const showInformationMessage = (..._args: any[]): Promise<string | undefined> =>
  Promise.resolve(undefined);
const showWarningMessage = (..._args: any[]): Promise<string | undefined> =>
  Promise.resolve(undefined);
const showErrorMessage = (..._args: any[]): Promise<string | undefined> =>
  Promise.resolve(undefined);
const showQuickPick = (..._args: any[]): Promise<unknown> => Promise.resolve(undefined);
const showInputBox = (..._args: any[]): Promise<string | undefined> =>
  Promise.resolve(undefined);

const window = {
  activeTextEditor: undefined as unknown,
  createStatusBarItem: (_id: string, _alignment: number, _priority: number) => ({
    text: "",
    tooltip: undefined,
    name: "",
    command: undefined,
    backgroundColor: undefined,
    show(): void {},
    hide(): void {},
    dispose(): void {},
  }),
  createOutputChannel: (_name: string) => ({
    append(_s: string): void {},
    appendLine(_s: string): void {},
    show(): void {},
    dispose(): void {},
  }),
  showInformationMessage,
  showWarningMessage,
  showErrorMessage,
  showQuickPick,
  showInputBox,
  setStatusBarMessage: (_s: string, _ms?: number) => ({ dispose(): void {} }),
  withProgress: <T>(_o: unknown, fn: (p: unknown, t: unknown) => Promise<T>): Promise<T> =>
    fn(
      { report(_x: unknown): void {} },
      { isCancellationRequested: false },
    ),
  registerTreeDataProvider: (_id: string, _p: unknown) => ({ dispose(): void {} }),
  showTextDocument: (_d: unknown, _o?: unknown): Promise<unknown> =>
    Promise.resolve({ edit: async (_cb: unknown) => true }),
};

const workspace = {
  textDocuments: [] as StubTextDocument[],
  getConfiguration(_section: string) {
    return {
      get<T>(_key: string, def?: T): T | undefined {
        return def;
      },
    };
  },
  onDidOpenTextDocument: (_cb: any) => ({ dispose(): void {} }),
  onDidChangeTextDocument: (_cb: any) => ({ dispose(): void {} }),
  onDidCloseTextDocument: (_cb: any) => ({ dispose(): void {} }),
  onDidChangeConfiguration: (_cb: any) => ({ dispose(): void {} }),
  openTextDocument: (_arg: any): Promise<StubTextDocument> =>
    Promise.resolve(makeStubDoc("")),
};

const env = {
  openExternal: (_uri: Uri): Promise<boolean> => Promise.resolve(true),
};

const commands = {
  registry: new Map<string, (...args: any[]) => any>(),
  registerCommand(name: string, cb: (...args: any[]) => any): { dispose(): void } {
    (this as any).registry.set(name, cb);
    return { dispose: (): void => void (this as any).registry.delete(name) };
  },
  executeCommand: (name: string, ...args: any[]): Promise<unknown> => {
    const fn = (commands as any).registry.get(name);
    if (!fn) return Promise.resolve(undefined);
    return Promise.resolve(fn(...args));
  },
};

const languages = {
  createDiagnosticCollection(_name: string) {
    const map = new Map<string, Diagnostic[]>();
    return {
      name: _name,
      set(uri: Uri, diags: Diagnostic[]): void {
        map.set(uri.toString(), diags);
      },
      get(uri: Uri): Diagnostic[] | undefined {
        return map.get(uri.toString());
      },
      delete(uri: Uri): void {
        map.delete(uri.toString());
      },
      clear(): void {
        map.clear();
      },
      dispose(): void {
        map.clear();
      },
    };
  },
  registerCodeActionsProvider: (
    _selector: any,
    _provider: any,
    _meta?: any,
  ) => ({ dispose(): void {} }),
};

enum ProgressLocation {
  SourceControl = 1,
  Window = 10,
  Notification = 15,
}

function makeStubDoc(text: string, uri = "file:///tmp/test.txt"): StubTextDocument {
  // Pre-index newline positions to allow positionAt() to be O(log n).
  const lines: number[] = [0];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "\n") lines.push(i + 1);
  }
  function positionAt(offset: number): Position {
    let lo = 0;
    let hi = lines.length - 1;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi + 1) / 2);
      if (lines[mid]! <= offset) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }
    return new Position(lo, offset - lines[lo]!);
  }
  return {
    uri: Uri.parse(uri),
    version: 1,
    lineCount: lines.length,
    getText(range?: Range): string {
      if (!range) return text;
      const start = lineOffset(range.start);
      const end = lineOffset(range.end);
      return text.slice(start, end);
    },
    positionAt,
  };
  function lineOffset(p: Position): number {
    return (lines[p.line] ?? 0) + p.character;
  }
}

const vscodeStub = {
  Position,
  Range,
  Diagnostic,
  DiagnosticSeverity,
  DiagnosticTag,
  Uri,
  MarkdownString,
  ThemeIcon,
  ThemeColor,
  TreeItem,
  TreeItemCollapsibleState,
  StatusBarAlignment,
  EventEmitter,
  CodeAction,
  CodeActionKind,
  ProgressLocation,
  CancellationTokenSource,
  window,
  workspace,
  env,
  commands,
  languages,
};

// Install the stub under the "vscode" module name. Works under
// both `import` (because esbuild/tsx use the CJS cache) and direct
// `require("vscode")`.
const originalResolve = (Module as any)._resolveFilename;
(Module as any)._resolveFilename = function (
  request: string,
  ...rest: any[]
): string {
  if (request === "vscode") return request;
  return originalResolve.call(this, request, ...rest);
};
const originalLoad = (Module as any)._load;
(Module as any)._load = function (
  request: string,
  ...rest: any[]
): any {
  if (request === "vscode") return vscodeStub;
  return originalLoad.call(this, request, ...rest);
};

export { vscodeStub, makeStubDoc };
