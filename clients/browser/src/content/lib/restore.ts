/**
 * MutationObserver-driven response restoration.
 *
 * After a model response renders, we walk every text node under the
 * conversation root for `<LABEL_XXXX>` placeholders, POST them to
 * `/v1/restore`, and swap the original text in place.
 *
 * Anti-flicker:
 *  - Batch DOM updates inside `requestAnimationFrame`.
 *  - Cache restored text by exact placeholder so re-rendered nodes don't
 *    re-request from the gateway.
 *  - Skip nodes whose text contains no placeholder match (cheap regex
 *    test BEFORE the network roundtrip).
 *
 * Boundary safety:
 *  - Streaming responses may split a placeholder across two text nodes
 *    (e.g. `<EMAIL_A2B3` in one chunk, `>` in the next). We delay
 *    restoration by a short debounce so the placeholder finishes
 *    streaming. If it never closes, no harm done — we never touch
 *    partial matches.
 */
import { restoreInBackground } from './messaging.js';

const PLACEHOLDER_RE = /<[A-Z][A-Z0-9_]*_[A-Z2-7]{4}>/g;
const DEBOUNCE_MS = 250;

export interface RestoreContext {
  requestId: string | null;
  /** Most recent scan-session id, set by the per-site content script. */
  setRequestId(id: string): void;
}

export interface RestoreManager {
  ctx: RestoreContext;
  /** Observe a subtree for placeholders; root defaults to document.body. */
  observe(root?: Element): () => void;
  detachAll(): void;
}

export function createRestoreManager(): RestoreManager {
  const cache = new Map<string, string>(); // placeholder -> original
  const observers = new Set<MutationObserver>();
  let timer: number | null = null;
  let lastRequestId: string | null = null;

  const ctx: RestoreContext = {
    get requestId() {
      return lastRequestId;
    },
    set requestId(v) {
      lastRequestId = v;
    },
    setRequestId(id: string) {
      lastRequestId = id;
    },
  };

  const scheduleSweep = (root: Element) => {
    if (timer !== null) clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      void sweep(root);
    }, DEBOUNCE_MS);
  };

  const sweep = async (root: Element): Promise<void> => {
    if (!ctx.requestId) return;
    const matches = collectPlaceholderNodes(root);
    if (matches.length === 0) return;
    // For each placeholder that isn't in the cache yet, ask the gateway
    // to restore JUST that placeholder. The response's `text` is the
    // original. Cheap because the gateway batches DB lookups internally
    // and the network round-trips for a typical chat are < 5.
    const allPlaceholders = new Set<string>();
    for (const m of matches) {
      for (const p of m.placeholders) allPlaceholders.add(p);
    }
    const need = [...allPlaceholders].filter((p) => !cache.has(p));
    await Promise.all(
      need.map(async (ph) => {
        try {
          const resp = await restoreInBackground(ctx.requestId!, ph);
          if (resp.restored > 0 && resp.text !== ph) {
            cache.set(ph, resp.text);
          }
        } catch {
          // Best-effort.
        }
      }),
    );
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => {
        for (const m of matches) applyToNode(m.node, cache);
      });
    } else {
      // Node / SSR fallback — just apply synchronously.
      for (const m of matches) applyToNode(m.node, cache);
    }
  };

  const startObserver = (root: Element): MutationObserver => {
    const o = new MutationObserver((records) => {
      let dirty = false;
      for (const r of records) {
        if (r.type === 'characterData') dirty = true;
        else if (r.type === 'childList' && (r.addedNodes.length > 0)) dirty = true;
        if (dirty) break;
      }
      if (dirty) scheduleSweep(root);
    });
    o.observe(root, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    observers.add(o);
    // Initial scan in case nodes are already there.
    scheduleSweep(root);
    return o;
  };

  return {
    ctx,
    observe(root) {
      const target = root ?? document.body;
      if (!target) {
        // Body not ready yet — wait for it.
        const stop = (): MutationObserver | null => {
          if (document.body) return startObserver(document.body);
          return null;
        };
        const tryStart = stop();
        if (tryStart) return () => tryStart.disconnect();
        const bootstrap = new MutationObserver(() => {
          if (document.body) {
            bootstrap.disconnect();
            startObserver(document.body);
          }
        });
        bootstrap.observe(document.documentElement, { childList: true });
        return () => bootstrap.disconnect();
      }
      const o = startObserver(target);
      return () => {
        o.disconnect();
        observers.delete(o);
      };
    },
    detachAll() {
      for (const o of observers) o.disconnect();
      observers.clear();
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    },
  };
}

interface PlaceholderMatch {
  node: Text;
  placeholders: string[];
}

function collectPlaceholderNodes(root: Element): PlaceholderMatch[] {
  /*
   * Walk text descendants manually rather than using TreeWalker.
   *
   * Why: happy-dom's TreeWalker.SHOW_TEXT filter is broken in 15.7
   * (returns 0 nodes), and a manual DFS is just as fast on a typical
   * conversation tree (<10k nodes). We avoid the divergence between
   * test and prod by always using the same iteration here.
   */
  const out: PlaceholderMatch[] = [];
  const stack: Node[] = [root];
  while (stack.length > 0) {
    const node = stack.pop()!;
    if (node.nodeType === 3 /* TEXT_NODE */) {
      const t = (node as Text).nodeValue ?? '';
      if (!t || !t.match(PLACEHOLDER_RE)) continue;
      const phs = t.match(PLACEHOLDER_RE) ?? [];
      if (phs.length > 0) out.push({ node: node as Text, placeholders: phs });
      continue;
    }
    if (node.nodeType !== 1 /* ELEMENT_NODE */) continue;
    const el = node as Element;
    const tag = el.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
    if (el.id === 'section-overlay-root') continue;
    // Push children in reverse so DFS visits them in source order.
    const children = el.childNodes;
    for (let i = children.length - 1; i >= 0; i -= 1) {
      const c = children[i];
      if (c) stack.push(c);
    }
  }
  return out;
}

function applyToNode(node: Text, cache: Map<string, string>): void {
  const before = node.nodeValue ?? '';
  if (!before) return;
  const after = before.replace(PLACEHOLDER_RE, (m) => cache.get(m) ?? m);
  if (after !== before) node.nodeValue = after;
}

/**
 * Exposed for tests so they can drive the algorithm with synthetic
 * DOMs / restore responses.
 */
export const _internal = {
  PLACEHOLDER_RE,
  DEBOUNCE_MS,
  collectPlaceholderNodes,
  applyToNode,
};
