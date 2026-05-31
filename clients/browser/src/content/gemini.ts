/**
 * gemini.google.com content script.
 *
 * Gemini's composer is a `<rich-textarea>` custom element wrapping a
 * `<div contenteditable>`. The send button is
 * `button[aria-label="Send message"]`.
 *
 * Gemini's React tree intercepts most keyboard events before they hit
 * our `keydown` capture, so the page-world fetch hook in `inject.ts` is
 * the canonical interception path for this site. The keyboard hook is
 * still wired for resilience.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge, scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest gemini.google.com markup.
const INPUT_SELECTORS = [
  'rich-textarea div[contenteditable="true"]',
  'div[aria-label="Enter a prompt here"][contenteditable="true"]',
  'div[role="textbox"][contenteditable="true"]',
];

const SEND_BUTTON_SELECTORS = [
  'button[aria-label="Send message"]',
  'button[aria-label="Send prompt"]',
  'button.send-button',
];

const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'gemini',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
});

injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    const scan = await scanInBackground('gemini', msg.url, msg.body);
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
