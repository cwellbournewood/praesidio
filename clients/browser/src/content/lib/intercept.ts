/**
 * Generic submit-interception primitives used by every per-site content
 * script. The site-specific files pass in selectors + a tagging string
 * (e.g. `'chatgpt'`) and we wire the rest.
 *
 * What this does:
 *  - Watch the document for the prompt textarea + send button.
 *  - Hook the textarea's `keydown` and the button's `click` so we can
 *    intercept submission BEFORE the page sends to the LLM provider.
 *  - On intercept: read the current prompt, ask the gateway to scan it,
 *    then either:
 *      • action=allow  → resume submission (replay the original event)
 *      • action=mask   → replace the textarea content with `sanitised`,
 *                        flash the mask overlay, then resume submission
 *      • action=block  → show block overlay, do NOT resume
 *
 * "Resume submission" is the trickiest part: we can't `dispatchEvent` a
 * fake click because React swallows non-trusted events. Instead, we
 * stamp a `data-praesidio-pass="<id>"` on the event we'd like to allow,
 * and when our hook sees that stamp on a subsequent event it bypasses.
 */
import type { SiteId, ScanResponse } from '../../lib/types.js';
import { renderBlockOverlay, renderMaskBanner, renderErrorOverlay } from './overlay.js';
import { scanInBackground } from './messaging.js';

export interface InterceptConfig {
  site: SiteId;
  /** CSS selectors that resolve the prompt input field. First match wins. */
  inputSelectors: string[];
  /** CSS selectors that resolve the send button. First match wins. */
  sendButtonSelectors: string[];
  /**
   * Force submission after the textarea is updated. Default just clicks
   * the send button; per-site files can override (e.g. Gemini needs to
   * dispatch a specific React-aware synthetic event).
   */
  resubmit?: (input: HTMLElement, button: HTMLElement | null) => void;
  /**
   * Read text from the input. Default reads `value` or `innerText`.
   */
  readText?: (input: HTMLElement) => string;
  /**
   * Write text into the input — must trigger React's controlled-input
   * onChange. Default uses the native value setter + `input` event.
   */
  writeText?: (input: HTMLElement, text: string) => void;
}

const PASS_ATTR = 'data-praesidio-pass';
const SESSION_ATTR = 'data-praesidio-session';

/**
 * Mint or reuse a stable session id for this tab. Stable across
 * scans within the same tab so `/v1/scan` can reuse the same vault
 * scope when the user sends multiple follow-up messages.
 */
function tabSessionId(): string {
  let id = document.documentElement.getAttribute(SESSION_ATTR);
  if (id) return id;
  // 12-byte random hex == 24 chars.
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  id = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  document.documentElement.setAttribute(SESSION_ATTR, id);
  return id;
}

function defaultRead(el: HTMLElement): string {
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
    return el.value;
  }
  return el.innerText;
}

function defaultWrite(el: HTMLElement, text: string): void {
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
    const proto =
      el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) {
      setter.call(el, text);
    } else {
      el.value = text;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }
  // contenteditable
  el.innerText = text;
  el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
}

function findFirst<T extends Element>(selectors: string[]): T | null {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el as T;
  }
  return null;
}

/**
 * Install submit hooks on the active document. Returns a cleanup
 * function. Idempotent — calling again replaces the existing hooks.
 */
export function installSubmitHook(cfg: InterceptConfig): () => void {
  const read = cfg.readText ?? defaultRead;
  const write = cfg.writeText ?? defaultWrite;

  /**
   * Pull the current prompt, scan it, apply the decision. Returns true
   * if the original submission should be allowed to proceed.
   */
  const intercept = async (e: Event): Promise<boolean> => {
    if (e instanceof Event && (e.target as HTMLElement | null)?.getAttribute(PASS_ATTR)) {
      return true;
    }
    const input = findFirst<HTMLElement>(cfg.inputSelectors);
    if (!input) return true;
    const text = read(input);
    if (!text || !text.trim()) return true;
    if (text === '__praesidio_heartbeat__') return true; // never re-scan our own probe

    e.preventDefault();
    e.stopPropagation();
    if (typeof (e as Event & { stopImmediatePropagation?: () => void }).stopImmediatePropagation === 'function') {
      (e as Event & { stopImmediatePropagation: () => void }).stopImmediatePropagation();
    }

    let resp: ScanResponse & { skipped?: true; error?: string };
    try {
      resp = await scanInBackground(cfg.site, location.href, text, tabSessionId());
    } catch (err) {
      renderErrorOverlay({
        message: err instanceof Error ? err.message : String(err),
        onRetry: () => {
          void intercept(e);
        },
      });
      return false;
    }
    if (resp.skipped) return true;

    if (resp.action === 'block') {
      renderBlockOverlay({
        reason: resp.reason ?? 'policy',
        severity: resp.severity ?? 'medium',
      });
      return false;
    }
    if (resp.action === 'mask' && resp.sanitised) {
      write(input, resp.sanitised);
      renderMaskBanner({ count: resp.transforms.length });
      // Re-fire submission via the configured resubmit path.
      requestAnimationFrame(() => {
        if (cfg.resubmit) {
          cfg.resubmit(input, findFirst<HTMLElement>(cfg.sendButtonSelectors));
        } else {
          const btn = findFirst<HTMLButtonElement>(cfg.sendButtonSelectors);
          if (btn) {
            btn.setAttribute(PASS_ATTR, '1');
            btn.click();
            setTimeout(() => btn.removeAttribute(PASS_ATTR), 0);
          }
        }
      });
      return false; // original event is consumed; resubmit fires a fresh one
    }
    // allow
    requestAnimationFrame(() => {
      if (cfg.resubmit) {
        cfg.resubmit(input, findFirst<HTMLElement>(cfg.sendButtonSelectors));
      } else {
        const btn = findFirst<HTMLButtonElement>(cfg.sendButtonSelectors);
        if (btn) {
          btn.setAttribute(PASS_ATTR, '1');
          btn.click();
          setTimeout(() => btn.removeAttribute(PASS_ATTR), 0);
        }
      }
    });
    return false;
  };

  const onKeydown = (e: KeyboardEvent) => {
    // Enter without Shift = send (universal across all 6 sites).
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    // Only intercept if the active element is one of our target inputs.
    const input = findFirst<HTMLElement>(cfg.inputSelectors);
    if (!input) return;
    if (e.target !== input && !input.contains(e.target as Node | null)) return;
    void intercept(e);
  };

  const onClick = (e: MouseEvent) => {
    const target = e.target as HTMLElement | null;
    if (!target) return;
    // Walk up — the button may have an icon child as actual target.
    const btn = target.closest(cfg.sendButtonSelectors.join(',')) as HTMLElement | null;
    if (!btn) return;
    if (btn.getAttribute(PASS_ATTR)) return;
    void intercept(e);
  };

  document.addEventListener('keydown', onKeydown, true);
  document.addEventListener('click', onClick, true);

  return () => {
    document.removeEventListener('keydown', onKeydown, true);
    document.removeEventListener('click', onClick, true);
  };
}

/** Exposed for tests so we can drive the flow with a fake DOM. */
export const _internal = {
  tabSessionId,
  defaultRead,
  defaultWrite,
  findFirst,
  PASS_ATTR,
  SESSION_ATTR,
};
