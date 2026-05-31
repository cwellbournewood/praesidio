/// <reference types="vitest" />
import { defineConfig, build } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, rmdirSync, unlinkSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));

const CONTENT_ENTRIES = [
  { name: 'content/chatgpt', input: 'src/content/chatgpt.ts' },
  { name: 'content/claude', input: 'src/content/claude.ts' },
  { name: 'content/gemini', input: 'src/content/gemini.ts' },
  { name: 'content/copilot', input: 'src/content/copilot.ts' },
  { name: 'content/perplexity', input: 'src/content/perplexity.ts' },
  { name: 'content/mistral', input: 'src/content/mistral.ts' },
  { name: 'content/inject', input: 'src/page/inject.ts' },
] as const;

/**
 * Section browser extension build config.
 *
 * Produces:
 *   dist/
 *     manifest.json            (copied + version-stamped from package.json)
 *     background.js            (service worker)
 *     content/<site>.js        (one per site)
 *     content/inject.js        (page-world script, isolated build)
 *     popup/index.html         (React popup)
 *     popup/popup.js
 *     icons/{16,32,48,128}.png
 *     _locales/<lang>/messages.json
 */
export default defineConfig({
  plugins: [
    react(),
    {
      // Custom plugin: copy manifest, icons, locales after build, and
      // relocate the popup HTML to dist/popup/index.html with
      // extension-relative asset paths. Also builds each content script
      // as a single-file IIFE so they work as MV3 content_scripts
      // (which don't support ESM imports).
      name: 'section-mv3-assets',
      async closeBundle() {
        const outDir = resolve(__dirname, 'dist');
        // Reentry guard — the per-content-script inner builds defined
        // below would trigger this hook again (Vite reuses the parent
        // plugin instance). Bail out cleanly the second time.
        const flag = '__section_mv3_assets_done';
        if ((globalThis as Record<string, unknown>)[flag]) return;
        (globalThis as Record<string, unknown>)[flag] = true;
        mkdirSync(outDir, { recursive: true });

        // manifest.json — stamp version from package.json
        const pkg = JSON.parse(
          readFileSync(resolve(__dirname, 'package.json'), 'utf8'),
        );
        const manifest = JSON.parse(
          readFileSync(resolve(__dirname, 'manifest.json'), 'utf8'),
        );
        manifest.version = pkg.version;
        writeFileSync(
          resolve(outDir, 'manifest.json'),
          JSON.stringify(manifest, null, 2),
          'utf8',
        );

        // icons
        const iconsSrc = resolve(__dirname, 'public/icons');
        const iconsDst = resolve(outDir, 'icons');
        mkdirSync(iconsDst, { recursive: true });
        if (existsSync(iconsSrc)) {
          for (const f of readdirSync(iconsSrc)) {
            copyFileSync(resolve(iconsSrc, f), resolve(iconsDst, f));
          }
        }

        // _locales
        const localesSrc = resolve(__dirname, 'public/_locales');
        const localesDst = resolve(outDir, '_locales');
        if (existsSync(localesSrc)) {
          for (const lang of readdirSync(localesSrc)) {
            const langSrc = resolve(localesSrc, lang);
            const langDst = resolve(localesDst, lang);
            mkdirSync(langDst, { recursive: true });
            for (const f of readdirSync(langSrc)) {
              copyFileSync(resolve(langSrc, f), resolve(langDst, f));
            }
          }
        }

        // Relocate dist/src/popup/index.html -> dist/popup/index.html.
        // Vite computed `../../...` paths because the source lived two
        // levels deep; after relocation we live one level deep, so we
        // strip one leading `../` from each script/link/style ref.
        const popupSrc = resolve(outDir, 'src/popup/index.html');
        const popupDst = resolve(outDir, 'popup/index.html');
        if (existsSync(popupSrc)) {
          mkdirSync(resolve(outDir, 'popup'), { recursive: true });
          // Originally `<script src="../../popup/popup.js">` etc.
          // After relocation, that becomes `../popup/popup.js` which
          // resolves correctly (../ goes back to dist, popup/popup.js
          // points into the popup folder) — but it's cleaner to use
          // `./popup.js` for sibling files. Rewrite both forms.
          const html = readFileSync(popupSrc, 'utf8')
            // Sibling: ../../popup/<file> -> ./<file>
            .replace(/(src|href)="\.\.\/\.\.\/popup\//g, '$1="./')
            // Non-sibling: ../../<dir>/<file> -> ../<dir>/<file>
            .replace(/(src|href)="\.\.\/\.\.\//g, '$1="../');
          writeFileSync(popupDst, html, 'utf8');
          // Best-effort cleanup of the now-empty dist/src/ tree.
          try {
            unlinkSync(popupSrc);
          } catch {
            // ignore
          }
          try {
            rmdirSync(resolve(outDir, 'src/popup'));
            rmdirSync(resolve(outDir, 'src'));
          } catch {
            // ignore — sibling files may still live there
          }
        }

        // Per-content-script IIFE bundles. Each one is a self-contained
        // file with no `import` statements so it runs as a classic
        // content script under MV3.
        const mode = process.env.NODE_ENV === 'development' ? 'development' : 'production';
        mkdirSync(resolve(outDir, 'content'), { recursive: true });
        for (const entry of CONTENT_ENTRIES) {
          const fileBase = entry.name.replace(/^content\//, '');
          await build({
            // Don't recurse into our plugin.
            plugins: [],
            mode,
            configFile: false,
            logLevel: 'warn',
            // Skip the auto-copy of public/ — those files already
            // landed in dist/ from the outer build; copying them into
            // dist/content/ would clutter the bundle.
            publicDir: false,
            build: {
              emptyOutDir: false,
              outDir: resolve(outDir, 'content'),
              target: 'es2022',
              minify: 'esbuild',
              sourcemap: false,
              lib: {
                entry: resolve(__dirname, entry.input),
                name: `Section_${fileBase}`,
                formats: ['iife'],
                fileName: () => `${fileBase}.js`,
              },
              rollupOptions: {
                output: {
                  inlineDynamicImports: true,
                  extend: true,
                },
                treeshake: true,
              },
            },
            resolve: {
              alias: { '@': resolve(__dirname, 'src') },
            },
          });
        }
      },
    },
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  // Extension-relative asset paths so the popup loads correctly from
  // `chrome-extension://<id>/popup/index.html`.
  base: '',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
    minify: 'esbuild',
    rollupOptions: {
      input: {
        background: resolve(__dirname, 'src/background/service-worker.ts'),
        'popup/index': resolve(__dirname, 'src/popup/index.html'),
      },
      output: {
        entryFileNames: (chunk) => {
          if (chunk.name === 'background') return 'background.js';
          if (chunk.name === 'popup/index') return 'popup/popup.js';
          return '[name].js';
        },
        chunkFileNames: 'shared/[name]-[hash].js',
        assetFileNames: (asset) => {
          if (asset.name && asset.name.endsWith('.html')) {
            return 'popup/[name][extname]';
          }
          return 'assets/[name][extname]';
        },
        format: 'es',
        inlineDynamicImports: false,
      },
    },
  },
  test: {
    environment: 'happy-dom',
    globals: false,
    include: ['tests/**/*.test.ts'],
    setupFiles: ['tests/setup.ts'],
  },
});
