#!/usr/bin/env node
/**
 * build-release — bundle the Web Store .zip, the signed .crx, the
 * updates.xml template, and INSTALL.md into a single
 * `section-extension-release-<ver>.zip` for one-download distribution.
 *
 * Run after build:zip and build:crx (or with --auto to chain).
 * Uses the same hand-rolled zip writer as build-zip.mjs — no extra deps.
 */
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateRawSync, crc32 } from 'node:zlib';
import { execSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const distZipDir = resolve(repoRoot, 'dist-zip');

const pkg = JSON.parse(readFileSync(resolve(repoRoot, 'package.json'), 'utf8'));
const version = pkg.version;

const wantAuto = process.argv.includes('--auto');

if (wantAuto) {
  console.log('build-release --auto: running build:zip + build:crx first');
  execSync('node scripts/build-zip.mjs', { cwd: repoRoot, stdio: 'inherit' });
  execSync('node scripts/build-crx.mjs', { cwd: repoRoot, stdio: 'inherit' });
}

const entries = [
  `section-browser-extension-${version}.zip`,
  `section-browser-extension-${version}.crx`,
  `updates.xml`,
  `INSTALL.md`,
];
const missing = entries.filter((n) => !existsSync(resolve(distZipDir, n)));
if (missing.length) {
  console.error(
    `Missing prerequisite files in dist-zip/:\n  ${missing.join('\n  ')}\n` +
      `Run \`npm run build:zip && npm run build:crx\` first, ` +
      `or pass --auto.`,
  );
  process.exit(1);
}

const releasePath = resolve(distZipDir, `section-extension-release-${version}.zip`);

function toDosDate(d) { return ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate(); }
function toDosTime(d) { return (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2); }

const centralEntries = [];
const localChunks = [];
let offset = 0;
const now = new Date();
const dosDate = toDosDate(now);
const dosTime = toDosTime(now);

for (const rel of entries) {
  const full = resolve(distZipDir, rel);
  const data = readFileSync(full);
  const compressed = deflateRawSync(data, { level: 9 });
  const crc = crc32(data);
  const nameBuf = Buffer.from(rel, 'utf8');

  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(0, 6);
  local.writeUInt16LE(8, 8);
  local.writeUInt16LE(dosTime, 10);
  local.writeUInt16LE(dosDate, 12);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(compressed.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(nameBuf.length, 26);
  local.writeUInt16LE(0, 28);
  localChunks.push(local, nameBuf, compressed);

  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(0, 8);
  central.writeUInt16LE(8, 10);
  central.writeUInt16LE(dosTime, 12);
  central.writeUInt16LE(dosDate, 14);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(compressed.length, 20);
  central.writeUInt32LE(data.length, 24);
  central.writeUInt16LE(nameBuf.length, 28);
  central.writeUInt16LE(0, 30);
  central.writeUInt16LE(0, 32);
  central.writeUInt16LE(0, 34);
  central.writeUInt16LE(0, 36);
  central.writeUInt32LE(0, 38);
  central.writeUInt32LE(offset, 42);
  centralEntries.push(Buffer.concat([central, nameBuf]));

  offset += local.length + nameBuf.length + compressed.length;
}

const central = Buffer.concat(centralEntries);
const eocd = Buffer.alloc(22);
eocd.writeUInt32LE(0x06054b50, 0);
eocd.writeUInt16LE(0, 4);
eocd.writeUInt16LE(0, 6);
eocd.writeUInt16LE(entries.length, 8);
eocd.writeUInt16LE(entries.length, 10);
eocd.writeUInt32LE(central.length, 12);
eocd.writeUInt32LE(offset, 16);
eocd.writeUInt16LE(0, 20);

const out = Buffer.concat([Buffer.concat(localChunks), central, eocd]);
mkdirSync(distZipDir, { recursive: true });
writeFileSync(releasePath, out);

console.log(`wrote ${releasePath} (${out.length} bytes, ${entries.length} files)`);
console.log('contents:');
for (const e of entries) console.log(`  - ${e}`);
