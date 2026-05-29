#!/usr/bin/env node
/**
 * Build + package the extension into a .vsix file using @vscode/vsce.
 *
 * Output: praesidio-vscode-<version>.vsix in the repo root for this
 * client. The Makefile picks the artefact up via `make vscode-package`.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

const vsceBin = resolve(
  root,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "vsce.cmd" : "vsce",
);
if (!existsSync(vsceBin)) {
  console.error(
    "vsce binary not found at",
    vsceBin,
    "- run `npm install` first.",
  );
  process.exit(1);
}

const child = spawn(vsceBin, ["package", "--no-yarn", "--allow-missing-repository"], {
  cwd: root,
  stdio: "inherit",
  // On Windows the npm-installed binary is `.cmd`, which Node refuses
  // to spawn without a shell. Harmless on POSIX.
  shell: process.platform === "win32",
});
child.on("exit", (code) => process.exit(code ?? 1));
