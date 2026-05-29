#!/usr/bin/env node
/**
 * build-zip — package `dist/` as `dist-zip/praesidio-browser-extension-<ver>.zip`
 * for Chrome Web Store / Edge Add-ons / Opera Add-ons submission.
 *
 * No external deps — we build the ZIP by hand (deflate per entry,
 * central directory, end-of-central-directory record). Keeps the lane
 * lean (avoid pulling in `archiver`/`adm-zip`).
 */
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateRawSync, crc32 } from 'node:zlib';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const distDir = resolve(repoRoot, 'dist');
const outDir = resolve(repoRoot, 'dist-zip');

const pkg = JSON.parse(readFileSync(resolve(repoRoot, 'package.json'), 'utf8'));
const version = pkg.version;
const zipPath = resolve(outDir, `praesidio-browser-extension-${version}.zip`);

if (!existsSync(distDir)) {
  console.error(`dist/ not found — run \`npm run build\` first.`);
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

const files = walk(distDir).sort();

function toDosDate(date) {
  return (
    ((date.getFullYear() - 1980) << 9) |
    ((date.getMonth() + 1) << 5) |
    date.getDate()
  );
}
function toDosTime(date) {
  return (
    (date.getHours() << 11) |
    (date.getMinutes() << 5) |
    Math.floor(date.getSeconds() / 2)
  );
}

const centralEntries = [];
const localChunks = [];
let offset = 0;
const now = new Date();
const dosDate = toDosDate(now);
const dosTime = toDosTime(now);

for (const f of files) {
  const rel = relative(distDir, f).replace(/\\/g, '/');
  const data = readFileSync(f);
  const compressed = deflateRawSync(data, { level: 9 });
  const crc = crc32(data);
  const nameBuf = Buffer.from(rel, 'utf8');

  // Local file header
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4); // version
  local.writeUInt16LE(0, 6); // gp flag
  local.writeUInt16LE(8, 8); // deflate
  local.writeUInt16LE(dosTime, 10);
  local.writeUInt16LE(dosDate, 12);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(compressed.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(nameBuf.length, 26);
  local.writeUInt16LE(0, 28);
  localChunks.push(local, nameBuf, compressed);

  // Central directory header
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4); // version made by
  central.writeUInt16LE(20, 6); // version needed
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
const centralOffset = offset;
const centralSize = central.length;

const eocd = Buffer.alloc(22);
eocd.writeUInt32LE(0x06054b50, 0);
eocd.writeUInt16LE(0, 4);
eocd.writeUInt16LE(0, 6);
eocd.writeUInt16LE(files.length, 8);
eocd.writeUInt16LE(files.length, 10);
eocd.writeUInt32LE(centralSize, 12);
eocd.writeUInt32LE(centralOffset, 16);
eocd.writeUInt16LE(0, 20);

const zip = Buffer.concat([Buffer.concat(localChunks), central, eocd]);
writeFileSync(zipPath, zip);
console.log(`wrote ${zipPath} (${zip.length} bytes, ${files.length} files)`);
