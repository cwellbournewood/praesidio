// Mirror ../docs/**/*.md into src/content/docs/ for Starlight.
//
// We keep the original markdown as the source of truth. This script:
//   1. Empties src/content/docs/ (except index.mdx).
//   2. Recursively copies every .md from ../docs/ into src/content/docs/,
//      lower-casing filenames and dropping the `.md` -> `.md` 1:1 mapping.
//   3. Rewrites a small set of relative links so Starlight routing works:
//        - `path/to/file.md`          -> `/path/to/file/`
//        - `path/to/file.md#anchor`   -> `/path/to/file/#anchor`
//      Anchors and external URLs are left alone.
//   4. Injects a frontmatter block if the source file lacks one, using
//      the first H1 as the title.
//
// Idempotent and dependency-free; runs before `astro build`.

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const srcDocs = path.join(repoRoot, "docs");
const outDocs = path.join(here, "..", "src", "content", "docs");

async function walk(dir) {
  const out = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await walk(full)));
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".md")) {
      out.push(full);
    }
  }
  return out;
}

function relPosix(p) {
  return p.split(path.sep).join("/");
}

async function emptyExceptIndex(dir) {
  await fs.mkdir(dir, { recursive: true });
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    if (entry.name === "index.mdx") continue;
    const target = path.join(dir, entry.name);
    await fs.rm(target, { recursive: true, force: true });
  }
}

function rewriteLinks(content) {
  // Markdown links: [text](path/to/file.md) or with #anchor / ?query.
  // Leave absolute URLs (http/https/mailto/etc) alone.
  return content.replace(
    /\]\((?!https?:|mailto:|tel:|#)([^)\s]+?)\.md(#[^)\s]*)?\)/g,
    (_, p, anchor) => `](/${p.toLowerCase()}/${anchor ?? ""})`,
  );
}

function ensureFrontmatter(content, fallbackTitle) {
  if (content.startsWith("---\n")) return content;
  let title = fallbackTitle;
  const m = content.match(/^#\s+(.+?)\s*$/m);
  if (m) title = m[1].trim();
  // Strip a leading H1 if we are also setting it in frontmatter; Starlight
  // will render its own title header.
  const stripped = content.replace(/^#\s+.+\n+/, "");
  const fm = `---\ntitle: ${JSON.stringify(title)}\n---\n\n`;
  return fm + stripped;
}

async function copyOne(src) {
  const rel = path.relative(srcDocs, src);
  const dst = path.join(outDocs, rel);
  await fs.mkdir(path.dirname(dst), { recursive: true });

  const raw = await fs.readFile(src, "utf8");
  const fallbackTitle = path
    .basename(rel, ".md")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const rewritten = rewriteLinks(raw);
  const final = ensureFrontmatter(rewritten, fallbackTitle);

  await fs.writeFile(dst, final, "utf8");
}

async function main() {
  try {
    await fs.access(srcDocs);
  } catch {
    console.error(`sync-docs: source not found: ${srcDocs}`);
    process.exit(1);
  }

  await emptyExceptIndex(outDocs);
  const files = await walk(srcDocs);
  for (const f of files) {
    await copyOne(f);
  }
  console.log(
    `sync-docs: mirrored ${files.length} markdown file(s) from ${relPosix(
      path.relative(here, srcDocs),
    )} -> ${relPosix(path.relative(here, outDocs))}`,
  );
}

main().catch((err) => {
  console.error("sync-docs failed:", err);
  process.exit(1);
});
