#!/usr/bin/env node
/**
 * build-crx — sign `dist/` into `dist-zip/section-browser-extension-<ver>.crx`
 * for operator self-host distribution (a private update server points at
 * this artifact).
 *
 * Uses `crx3` (Chrome's current CRX_v3 format). If the package is not
 * installed (`npm install crx3`), or if no signing key is available on
 * disk, we emit a friendly message and exit zero — this is best-effort
 * for dev installs.
 *
 * Key resolution order:
 *   1. $SECTION_CRX_KEY  (path to a PEM file)
 *   2. ./key.pem            (relative to clients/browser/)
 *   3. generated key.pem    (written if missing; gitignored)
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const distDir = resolve(repoRoot, 'dist');
const outDir = resolve(repoRoot, 'dist-zip');

const pkg = JSON.parse(readFileSync(resolve(repoRoot, 'package.json'), 'utf8'));
const version = pkg.version;
const crxPath = resolve(outDir, `section-browser-extension-${version}.crx`);

if (!existsSync(distDir)) {
  console.error(`dist/ not found — run \`npm run build\` first.`);
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });

// Try to load crx3.
let crx3;
try {
  crx3 = (await import('crx3')).default ?? (await import('crx3'));
} catch (err) {
  console.warn(
    'crx3 is not installed; skipping .crx packaging. ' +
      'Install with `npm install crx3` to enable self-host signing.',
  );
  process.exit(0);
}

const keyPath =
  process.env.SECTION_CRX_KEY ?? resolve(repoRoot, 'key.pem');

if (!existsSync(keyPath)) {
  console.warn(`Signing key not found at ${keyPath}; generating one.`);
  try {
    // openssl is widely available; fall back to a Node implementation
    // if it isn't.
    execSync(`openssl genrsa -out "${keyPath}" 2048`, { stdio: 'pipe' });
  } catch {
    const { generateKeyPairSync } = await import('node:crypto');
    const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    writeFileSync(
      keyPath,
      privateKey.export({ type: 'pkcs1', format: 'pem' }),
    );
  }
  console.warn(
    `Wrote ${keyPath}. KEEP THIS FILE SECRET — it pins your extension ID.`,
  );
}

await crx3([distDir], {
  keyPath,
  crxPath,
  zipPath: resolve(outDir, `section-browser-extension-${version}-unsigned.zip`),
});
console.log(`wrote ${crxPath}`);
