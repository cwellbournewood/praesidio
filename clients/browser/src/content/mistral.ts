/**
 * chat.mistral.ai content script.
 *
 * Mistral's composer is a `<textarea>` inside a wrapper with
 * `data-testid="chat-textarea"`. Send is `button[type="submit"]` inside
 * the same form, or `button[aria-label="Send"]`.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge, scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest chat.mistral.ai markup.
const INPUT_SELECTORS = [
  'textarea[data-testid="chat-textarea"]',
  'textarea[placeholder*="Ask"]',
  'div[contenteditable="true"][role="textbox"]',
];

const SEND_BUTTON_SELECTORS = [
  'button[type="submit"][aria-label*="end"]',
  'button[aria-label="Send"]',
  'button[type="submit"]',
];

const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'mistral',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
});

injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    const scan = await scanInBackground('mistral', msg.url, msg.body);
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
