/**
 * Manages a child `praesidio-edge-proxy` process.
 *
 *  - `start()` spawns the binary with --gateway / --api-key / --port.
 *  - `stop()` sends SIGTERM (Windows: kill) and waits for exit (with
 *    a 5s grace then SIGKILL).
 *  - `state` reflects the current child status; subscribers can listen
 *    to `onStateChange` to update the status bar.
 *
 * The binary itself is shipped separately (lane E). We only spawn it;
 * if it isn't on PATH we surface a clear error.
 */

import { spawn, type ChildProcess } from "node:child_process";
import * as vscode from "vscode";

import type { ProxyState } from "../lib/types.js";

export interface ProxyControllerOpts {
  binaryPath: string;
  gatewayUrl: string;
  port: number;
  apiKey?: string | null;
  bearerToken?: string | null;
  /** OutputChannel for stdout/stderr; defaults to a new "Praesidio Proxy" channel. */
  output?: vscode.OutputChannel;
}

export class ProxyController {
  private child: ChildProcess | undefined;
  private _state: ProxyState = "stopped";
  private readonly emitter = new vscode.EventEmitter<ProxyState>();
  readonly onStateChange = this.emitter.event;
  private readonly output: vscode.OutputChannel;
  private ownsOutput = false;

  constructor(output?: vscode.OutputChannel) {
    if (output) {
      this.output = output;
    } else {
      this.output = vscode.window.createOutputChannel("Praesidio Proxy");
      this.ownsOutput = true;
    }
  }

  get state(): ProxyState {
    return this._state;
  }

  async start(opts: ProxyControllerOpts): Promise<void> {
    if (this._state === "running" || this._state === "starting") {
      throw new Error("proxy is already running");
    }
    this.setState("starting");
    const args = [
      "start",
      "--gateway",
      opts.gatewayUrl,
      "--port",
      String(opts.port),
    ];
    if (opts.apiKey) {
      args.push("--api-key", opts.apiKey);
    } else if (opts.bearerToken) {
      args.push("--bearer", opts.bearerToken);
    }
    this.output.appendLine(
      `> ${opts.binaryPath} ${args.map(redact).join(" ")}`,
    );

    let child: ChildProcess;
    try {
      child = spawn(opts.binaryPath, args, {
        stdio: ["ignore", "pipe", "pipe"],
        shell: false,
        windowsHide: true,
      });
    } catch (err) {
      this.setState("error");
      const m = err instanceof Error ? err.message : String(err);
      this.output.appendLine(`spawn failed: ${m}`);
      throw new Error(`praesidio-edge-proxy could not be spawned: ${m}`);
    }

    this.child = child;

    child.stdout?.on("data", (b: Buffer) =>
      this.output.append(b.toString("utf-8")),
    );
    child.stderr?.on("data", (b: Buffer) =>
      this.output.append(b.toString("utf-8")),
    );
    child.once("error", (err) => {
      this.output.appendLine(`proxy error: ${err.message}`);
      this.setState("error");
    });
    child.once("exit", (code, signal) => {
      this.output.appendLine(
        `proxy exited (code=${code ?? "null"} signal=${signal ?? "null"})`,
      );
      this.child = undefined;
      // Only treat unexpected exit as error.
      this.setState(this._state === "stopped" ? "stopped" : "error");
    });

    // Give the proxy a moment to fail fast (e.g. binary missing).
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => {
        if (this.child && !this.child.killed) {
          this.setState("running");
          resolve();
        }
      }, 250);
      child.once("error", (err) => {
        clearTimeout(t);
        reject(err);
      });
      child.once("exit", (code, signal) => {
        clearTimeout(t);
        if (this._state !== "running") {
          reject(
            new Error(
              `proxy exited before ready (code=${code} signal=${signal})`,
            ),
          );
        }
      });
    });
  }

  async stop(): Promise<void> {
    if (this._state === "stopped") return;
    if (!this.child) {
      this.setState("stopped");
      return;
    }
    const child = this.child;
    this.setState("stopped");
    try {
      child.kill(process.platform === "win32" ? undefined : "SIGTERM");
    } catch (err) {
      this.output.appendLine(
        `proxy kill failed: ${(err as Error).message}`,
      );
    }
    await new Promise<void>((resolve) => {
      const t = setTimeout(() => {
        try {
          child.kill("SIGKILL");
        } catch {}
        resolve();
      }, 5000);
      child.once("exit", () => {
        clearTimeout(t);
        resolve();
      });
    });
    this.child = undefined;
  }

  dispose(): void {
    void this.stop();
    this.emitter.dispose();
    if (this.ownsOutput) this.output.dispose();
  }

  private setState(s: ProxyState): void {
    if (s === this._state) return;
    this._state = s;
    this.emitter.fire(s);
  }
}

/** Redact API keys / bearer tokens in args before logging. */
function redact(arg: string): string {
  if (arg.startsWith("eyJ") || arg.length > 32) return "<redacted>";
  return arg;
}
