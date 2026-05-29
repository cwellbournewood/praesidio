/**
 * Content-script side of the runtime bridge.
 *
 * Two channels:
 *
 *   - chrome.runtime.sendMessage — to/from the background service
 *     worker. Used for the actual scan/restore calls (so secrets stay in
 *     the worker context, not the content script).
 *   - window.postMessage — to/from the page-world `inject.ts` script,
 *     used so we can monkey-patch fetch in the page context (the only
 *     way to intercept React-controlled inputs reliably).
 *
 * Both ends prefix messages with PAGE_BRIDGE_TAG so we ignore unrelated
 * traffic. We also check `event.source === window` and
 * `event.origin === window.location.origin` on incoming page messages.
 */
import {
  PAGE_BRIDGE_TAG,
  type PageBridgeMessage,
  type RestoreResponse,
  type RuntimeMessage,
  type ScanResponse,
  type SiteId,
} from '../../lib/types.js';

export async function scanInBackground(
  site: SiteId,
  url: string,
  text: string,
  sessionId?: string,
): Promise<ScanResponse & { skipped?: true; error?: string }> {
  const msg: RuntimeMessage = { type: 'scan', site, url, text, sessionId };
  return chrome.runtime.sendMessage(msg);
}

export async function restoreInBackground(
  requestId: string,
  text: string,
): Promise<RestoreResponse & { error?: string }> {
  const msg: RuntimeMessage = { type: 'restore', request_id: requestId, text };
  return chrome.runtime.sendMessage(msg);
}

// ---------------------------------------------------------------------------
// Page-world bridge.
// ---------------------------------------------------------------------------

export type PageBridgeHandler = (msg: PageBridgeMessage) => void | Promise<void>;

export interface PageBridge {
  /** Send a typed message INTO the page world. */
  send(msg: PageBridgeMessage): void;
  /** Tear down listeners. */
  detach(): void;
}

export function installPageBridge(handler: PageBridgeHandler): PageBridge {
  const onMessage = (event: MessageEvent) => {
    if (event.source !== window) return;
    if (event.origin && event.origin !== window.location.origin) return;
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if ((data as { tag?: unknown }).tag !== PAGE_BRIDGE_TAG) return;
    void handler(data as PageBridgeMessage);
  };
  window.addEventListener('message', onMessage);
  return {
    send(msg) {
      window.postMessage(msg, window.location.origin);
    },
    detach() {
      window.removeEventListener('message', onMessage);
    },
  };
}

/**
 * Inject the page-world script (`content/inject.js`, declared as a
 * web_accessible_resource). It runs in the page realm so it can patch
 * `window.fetch` — content scripts run in an isolated realm and would
 * not affect the page's own fetch reference.
 */
export function injectPageScript(): void {
  try {
    const src = chrome.runtime.getURL('content/inject.js');
    if (document.querySelector(`script[data-praesidio-inject="${src}"]`)) return;
    const s = document.createElement('script');
    s.src = src;
    s.async = false;
    s.dataset.praesidioInject = src;
    (document.head ?? document.documentElement).appendChild(s);
    s.addEventListener('load', () => s.remove());
  } catch {
    // Injection can fail on pages with strict CSP. The DOM-walk
    // intercept in content/lib/intercept.ts is the fallback.
  }
}
