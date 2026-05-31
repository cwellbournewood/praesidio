/**
 * claude.ai content script.
 *
 * Claude's composer is a ProseMirror contenteditable, not a textarea.
 * The send button has `aria-label="Send Message"` on the desktop layout
 * (capital M) — newer builds drop the capital.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge, scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest claude.ai markup.
const INPUT_SELECTORS = [
  'div[contenteditable="true"].ProseMirror',
  'div[contenteditable="true"][data-placeholder]',
  'div[role="textbox"][contenteditable="true"]',
];

const SEND_BUTTON_SELECTORS = [
  'button[aria-label="Send Message"]',
  'button[aria-label="Send message"]',
  'button[data-testid="send-button"]',
];

const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'claude',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
  readText(el) {
    // ProseMirror keeps each paragraph in its own `<p>`. We join with
    // newlines to preserve the user's intended line breaks.
    if (el instanceof HTMLDivElement) {
      const paras = el.querySelectorAll<HTMLElement>('p');
      if (paras.length > 0) {
        return Array.from(paras, (p) => p.innerText).join('\n');
      }
    }
    return el instanceof HTMLTextAreaElement ? el.value : el.innerText;
  },
  writeText(el, text) {
    if (el instanceof HTMLTextAreaElement) {
      el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return;
    }
    // ProseMirror: we need to clear children and insert a single paragraph
    // node with the sanitised text. ProseMirror watches `input` events.
    el.innerHTML = '';
    const p = document.createElement('p');
    p.textContent = text;
    el.appendChild(p);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
  },
});

injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    const scan = await scanInBackground('claude', msg.url, msg.body);
    if (scan.skipped) {
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'allow', sanitisedBody: msg.body });
      return;
    }
    if (scan.action === 'block') {
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'block', sanitisedBody: null, reason: scan.reason, severity: scan.severity });
      return;
    }
    if (scan.action === 'mask') {
      restore.ctx.setRequestId(scan.request_id);
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'mask', sanitisedBody: scan.sanitised ?? msg.body });
      return;
    }
    bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'allow', sanitisedBody: msg.body });
  } else if (msg.kind === 'restore.request') {
    const resp = await restoreInBackground(msg.request_id, msg.text);
    bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'restore.response', id: msg.id, text: resp.text, restored: resp.restored, missing: resp.missing });
  }
});

window.addEventListener('beforeunload', () => {
  cleanupSubmit();
  bridge.detach();
  restore.detachAll();
});
