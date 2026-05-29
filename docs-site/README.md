# Praesidio docs site

Static documentation site built with **Astro + Starlight**.

## Why Astro Starlight?

- Purpose-built for docs (sidebar, search, dark mode, edit-on-github,
  i18n, last-updated) with zero custom code.
- File-based content collection in plain Markdown / MDX — our existing
  `docs/` tree mirrors 1:1 into `src/content/docs/`.
- Generates a static site (`dist/`) — trivial to host on GitHub Pages,
  Cloudflare Pages, S3 + CloudFront, or `kubectl cp` into an nginx
  sidecar.
- Independent of the Next.js admin UI — no risk of coupling the docs
  release cadence to product UI changes.

VitePress was the other strong candidate; it would also work, but the
sidebar autogeneration in Starlight, plus first-class `astro:content`
schemas, made for a slightly simpler mirror of the existing `docs/`
layout.

## Build

```bash
# From the docs-site/ directory
pnpm install
pnpm build      # runs prebuild sync, then writes dist/

# From the repo root, using the Makefile
make docs       # equivalent
```

Output lands in `docs-site/dist/`.

## Development

```bash
pnpm dev        # http://localhost:4321
```

The `prebuild` script (`scripts/sync-docs.mjs`) copies `../docs/**/*.md`
into `src/content/docs/`, rewriting a few link patterns so internal
references resolve against Starlight's routing. The source of truth for
all content remains in the repo's top-level `docs/` directory.
